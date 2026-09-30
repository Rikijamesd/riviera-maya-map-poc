"""Glide: listing photos -> ~30s parallax walkthrough video. CPU only, no paid AI.

Pipeline
  1. prep     resize, auto brightness/contrast, crop to 16:9 / 9:16 / 1:1
  2. depth    Depth Anything V2 *Small* (Apache-2.0) via ONNX Runtime
  3. render   5s depth-parallax camera move per photo (move in/back + drift, rise, orbit), OpenCV
  4. stitch   FFmpeg crossfades + info lower-third + branded end card + music fade-out
  5. export   H.264 MP4 in the chosen aspect ratio

Built around VideoJob + build_video() so a later RQ worker / FastAPI endpoint can
call it directly; main() is just a CLI wrapper.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent

# Only the Small checkpoint is Apache-2.0. Base/Large/Giant are CC-BY-NC-4.0
# (non-commercial) - do not swap this URL for them.
DEPTH_MODEL_URL = (
    "https://huggingface.co/onnx-community/depth-anything-v2-small/"
    "resolve/main/onnx/model.onnx"
)
DEPTH_MODEL_PATH = HERE / "models" / "depth_anything_v2_small.onnx"

ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
MOVES = ["push-right", "push-left", "pull-right", "pull-left", "rise-push", "orbit-right", "orbit-left", "push-in"]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass
class VideoJob:
    photos: list[Path]
    out: Path
    aspect: str = "16:9"
    fps: int = 30
    clip_seconds: float = 5.0
    crossfade: float = 0.8
    moves: list[str] = field(default_factory=lambda: ["auto"])
    intensity: float = 1.0
    enhance: bool = True
    depth_mode: str = "model"  # "model" | "gradient" (no-model fallback for quick tests)
    draft: bool = False  # 720p-class output, ~2x faster
    # overlays
    price: str | None = None
    beds: str | None = None
    baths: str | None = None
    area: str | None = None
    location: str | None = None
    # end card
    broker_name: str | None = None
    phone: str | None = None
    logo: Path | None = None
    tagline: str | None = None
    brand_color: str = "#0f2a3a"
    endcard_seconds: float = 4.0
    # audio
    music: Path | None = None
    music_fade: float = 3.0
    font: Path | None = None
    keep_work: Path | None = None  # keep intermediate clips/depth maps here

    @property
    def size(self) -> tuple[int, int]:
        w, h = ASPECTS[self.aspect]
        return (w * 2 // 3, h * 2 // 3) if self.draft else (w, h)


# --------------------------------------------------------------------------- #
# 1. Prep
# --------------------------------------------------------------------------- #

def load_photo(path: Path) -> np.ndarray:
    """RGB uint8, EXIF rotation applied."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    return np.asarray(img)


def auto_enhance(rgb: np.ndarray) -> np.ndarray:
    """Gentle auto levels + brightness + local contrast, tuned for interiors.

    Deliberately conservative: listing photos are often already edited and an
    overcooked HDR look reads as cheap.
    """
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    L = lab[..., 0].astype(np.float32)

    # Auto levels on luminance, blended 70% so we don't clip deliberate shadows.
    lo, hi = np.percentile(L, (0.5, 99.5))
    if hi - lo > 20:
        stretched = np.clip((L - lo) * 255.0 / (hi - lo), 0, 255)
        L = 0.3 * L + 0.7 * stretched

    # Brighten dark photos toward a mid-grey mean (gamma limited to 0.7..1.0).
    mean = L.mean() / 255.0
    if mean < 0.45:
        gamma = float(np.clip(math.log(0.47) / math.log(max(mean, 1e-3)), 0.7, 1.0))
        L = 255.0 * (L / 255.0) ** gamma

    # Local contrast (CLAHE) at half strength.
    L8 = np.clip(L, 0, 255).astype(np.uint8)
    clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8)).apply(L8)
    lab[..., 0] = cv2.addWeighted(L8, 0.5, clahe, 0.5, 0)
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)

    # +8% saturation.
    hsv = cv2.cvtColor(out, cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.08, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)


def crop_to_aspect(rgb: np.ndarray, w: int, h: int) -> np.ndarray:
    """Centre crop to w:h."""
    ih, iw = rgb.shape[:2]
    target = w / h
    if iw / ih > target:
        cw = int(round(ih * target))
        x0 = (iw - cw) // 2
        return rgb[:, x0:x0 + cw]
    ch = int(round(iw / target))
    y0 = (ih - ch) // 2
    return rgb[y0:y0 + ch]


def prep_photo(path: Path, job: VideoJob, supersample: float) -> np.ndarray:
    """Load -> enhance -> crop -> resize to output size * supersample. Returns BGR."""
    rgb = load_photo(path)
    if job.enhance:
        rgb = auto_enhance(rgb)
    w, h = job.size
    rgb = crop_to_aspect(rgb, w, h)
    sw, sh = int(round(w * supersample)), int(round(h * supersample))
    interp = cv2.INTER_AREA if rgb.shape[1] > sw else cv2.INTER_LANCZOS4
    rgb = cv2.resize(rgb, (sw, sh), interpolation=interp)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


# --------------------------------------------------------------------------- #
# 2. Depth
# --------------------------------------------------------------------------- #

class DepthEstimator:
    """Depth Anything V2 Small on ONNX Runtime (CPU). Returns relative disparity."""

    MEAN = np.array([0.485, 0.456, 0.406], np.float32)
    STD = np.array([0.229, 0.224, 0.225], np.float32)

    def __init__(self, model_path: Path = DEPTH_MODEL_PATH, input_size: int = 518):
        import onnxruntime as ort

        ensure_depth_model(model_path)
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(
            str(model_path), opts, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.sess.get_inputs()[0].name
        self.input_size = input_size

    def __call__(self, bgr: np.ndarray) -> np.ndarray:
        h, w = bgr.shape[:2]
        # Short side -> input_size, both sides multiples of 14 (ViT patch size).
        s = self.input_size / min(h, w)
        nh = max(14, int(round(h * s / 14)) * 14)
        nw = max(14, int(round(w * s / 14)) * 14)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        x = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
        x = ((x - self.MEAN) / self.STD).transpose(2, 0, 1)[None]
        pred = self.sess.run(None, {self.input_name: x})[0]
        pred = np.squeeze(pred).astype(np.float32)  # (nh, nw), larger = closer
        return cv2.resize(pred, (w, h), interpolation=cv2.INTER_CUBIC)


def ensure_depth_model(path: Path) -> None:
    if path.exists() and path.stat().st_size > 1_000_000:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Depth Anything V2 Small (~99 MB, Apache-2.0) -> {path}")
    tmp = path.with_suffix(".part")
    urllib.request.urlretrieve(DEPTH_MODEL_URL, tmp)
    tmp.replace(path)


def gradient_depth(bgr: np.ndarray) -> np.ndarray:
    """No-model fallback: floor (bottom) near, ceiling (top) far."""
    h, w = bgr.shape[:2]
    return np.repeat(np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None], w, axis=1)


def clean_disparity(raw: np.ndarray) -> np.ndarray:
    """Normalise to 0..1 (1 = nearest) and soften edges so the warp doesn't tear.

    A small max-filter grows foreground slightly, so object edges carry their own
    pixels instead of dragging the background along with them.
    """
    lo, hi = np.percentile(raw, (2, 98))
    d = np.clip((raw - lo) / max(hi - lo, 1e-6), 0, 1).astype(np.float32)
    k = max(3, int(min(d.shape) * 0.006) | 1)
    d = cv2.dilate(d, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    # Light blur only: a wide one spreads the stretch at object edges across the background
    # (reads as jelly); a narrow one keeps it to a thin band the eye doesn't catch.
    d = cv2.GaussianBlur(d, (0, 0), sigmaX=k * 0.35)
    return d


# --------------------------------------------------------------------------- #
# 3. Parallax render
# --------------------------------------------------------------------------- #

@dataclass
class MoveCurve:
    """Camera state as functions of eased time e in [0, 1].

    Forward model (output px q centred, source point p centred, in output px units):
        q = (p * zoom + parallax * d_rel(p) * size) / (1 - dolly * d_rel(p)) + pan * size
    This is the pinhole-camera translation formula with d_rel standing in for inverse depth.
    Because d_rel is (up to the model's unknown scale/shift) affine in true inverse depth, and
    inverse depth is affine across any flat surface, the map is projective on walls, floors and
    ceilings - straight lines stay straight. (A multiplicative (1 + dolly*d) form bends them.)
    zoom:     global scale (all depths)
    dolly:    extra scale for near pixels (push-in / pull-back parallax)
    pan:      global shift, fraction of width/height (all depths)
    parallax: extra shift for near pixels, fraction of width/height
    """

    zoom: Callable[[float], float]
    dolly: Callable[[float], float]
    pan: Callable[[float], tuple[float, float]]
    parallax: Callable[[float], tuple[float, float]]
    focus_pct: float  # disparity percentile that stays still (the focal plane)


def make_move(name: str, k: float) -> MoveCurve:
    """Combined moves, the way a camera operator shoots a walkthrough (travel + drift).

    Leans on dolly/parallax (depth-dependent) rather than flat zoom/pan, which reads as a
    moving photo. Focus near the back wall anchors the background; orbits pivot mid-room.
    Kept in sync with makeMove() in tlrm's src/lib/glideVideo.ts.
    """
    spec = {
        "push-right": (1, (-1, 0), False), "push-left": (1, (1, 0), False),
        "pull-right": (-1, (-1, 0), False), "pull-left": (-1, (1, 0), False),
        "rise-push": (1, (0, 1), False),
        "orbit-right": (0.4, (-1, 0), True), "orbit-left": (0.4, (1, 0), True),
        "push-in": (1, (0, 0), False),
    }
    travel, (dx, dy), orbit = spec[name]

    def along(e: float) -> float:
        return (e if travel >= 0 else 1 - e) * abs(travel)

    # Most of the travel is global (zoom/pan: every pixel moves together, can't distort); depth
    # parallax is a subtle layer on top. A single photo has nothing behind the sofa, so strong
    # parallax has to stretch pixels at object edges - the "rubbery" look.
    par_a = 0.04 if orbit else 0.025
    pan_a = 0.02 if orbit else 0.05
    return MoveCurve(
        zoom=lambda e: 1 + 0.18 * k * along(e),
        dolly=lambda e: 0.07 * k * along(e),
        pan=lambda e: (dx * pan_a * k * (2 * e - 1), dy * pan_a * k * (2 * e - 1)),
        parallax=lambda e: (dx * par_a * k * (2 * e - 1), dy * par_a * k * (2 * e - 1)),
        focus_pct=50 if orbit else 10,
    )


def ease(t: float) -> float:
    """Mostly linear (reads as a real dolly), softened at the ends."""
    return 0.6 * t + 0.4 * (0.5 - 0.5 * math.cos(math.pi * t))


def render_clip(
    src: np.ndarray, disp: np.ndarray, move: MoveCurve, job: VideoJob,
    write_frame: Callable[[np.ndarray], None],
) -> None:
    W, H = job.size
    sh, sw = src.shape[:2]
    scale = sw / W  # source px per output px
    n = int(round(job.clip_seconds * job.fps))

    d_rel = disp - np.percentile(disp, move.focus_pct)
    d_min, d_max = float(d_rel.min()), float(d_rel.max())

    # Edge-gap guard: the constant extra zoom that keeps every sample inside the source for
    # the whole move (constant, so the motion stays smooth). The source point behind an edge
    # pixel is linear in d, so both edges at the nearest/farthest disparity are the worst case.
    need = 1.0
    for i in range(n):
        e = ease(i / max(n - 1, 1))
        z, dl = move.zoom(e), move.dolly(e)
        (px, py), (tx, ty) = move.pan(e), move.parallax(e)
        for pan_a, par_a in ((px, tx), (py, ty)):
            for edge in (-0.5, 0.5):
                for d in (d_min, d_max):
                    p = ((edge - pan_a) * (1 - dl * d) - par_a * d) / z
                    need = max(need, abs(p) / 0.5)
    zoom_fix = need * 1.005

    # Maps are computed at half res (they're smooth) then upsampled; the colour
    # remap happens at full res from the supersampled source.
    mw, mh = W // 2, H // 2
    ux, uy = np.meshgrid(
        (np.arange(mw, dtype=np.float32) + 0.5) * (W / mw) - W / 2,
        (np.arange(mh, dtype=np.float32) + 0.5) * (H / mh) - H / 2,
    )
    d_rel_src = d_rel.astype(np.float32)
    cx, cy = sw / 2 - 0.5, sh / 2 - 0.5

    for i in range(n):
        e = ease(i / max(n - 1, 1))
        z = move.zoom(e) * zoom_fix
        dl = move.dolly(e)
        (px, py), (tx, ty) = move.pan(e), move.parallax(e)

        # Backward warp by fixed-point iteration: p = (b * (1 - dolly*d) - parallax*d) / zoom.
        bx = ux - px * W
        by = uy - py * H
        p_x, p_y = bx / z, by / z
        for _ in range(4):
            d = cv2.remap(d_rel_src, cx + p_x * scale, cy + p_y * scale,
                          cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            p_x = (bx * (1 - dl * d) - tx * W * d) / z
            p_y = (by * (1 - dl * d) - ty * H * d) / z

        map_x = cv2.resize(cx + p_x * scale, (W, H), interpolation=cv2.INTER_LINEAR)
        map_y = cv2.resize(cy + p_y * scale, (W, H), interpolation=cv2.INTER_LINEAR)
        frame = cv2.remap(src, map_x, map_y, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        write_frame(frame)


# --------------------------------------------------------------------------- #
# 4. Overlays / end card (PIL -> PNG, composited by FFmpeg)
# --------------------------------------------------------------------------- #

FONT_CANDIDATES = {
    "bold": [
        "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ],
    "regular": [
        "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ],
}


def load_font(job: VideoJob, weight: str, size: int) -> ImageFont.FreeTypeFont:
    paths = ([str(job.font)] if job.font else []) + FONT_CANDIDATES[weight]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def info_lines(job: VideoJob) -> list[tuple[str, str]]:
    specs = [s for s in (
        f"{job.beds} bd" if job.beds else None,
        f"{job.baths} ba" if job.baths else None,
        job.area,
    ) if s]
    lines = []
    if job.price:
        lines.append(("bold", job.price))
    if specs:
        lines.append(("regular", "  \u00b7  ".join(specs)))
    if job.location:
        lines.append(("regular", job.location))
    return lines


def make_info_overlay(job: VideoJob, path: Path) -> bool:
    lines = info_lines(job)
    if not lines:
        return False
    W, H = job.size
    u = min(W, H)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # Soft dark gradient behind the text for legibility on bright photos.
    grad_h = int(H * 0.45)
    alpha = (np.linspace(0, 1, grad_h) ** 1.6 * 170).astype(np.uint8)
    band = np.zeros((grad_h, W, 4), np.uint8)
    band[..., 3] = alpha[:, None]
    # 9:16 -> keep text above the Reels/TikTok caption zone.
    bottom_margin = int(H * 0.20) if H > W else int(u * 0.08)
    img.alpha_composite(Image.fromarray(band), (0, H - grad_h))

    draw = ImageDraw.Draw(img)
    x = int(u * 0.07)
    sizes = {"bold": int(u * 0.075), "regular": int(u * 0.04)}
    fonts = {w: load_font(job, w, s) for w, s in sizes.items()}
    heights = [fonts[w].getbbox(t)[3] for w, t in lines]
    gap = int(u * 0.018)
    y = H - bottom_margin - sum(heights) - gap * (len(lines) - 1)
    for (w, t), lh in zip(lines, heights):
        draw.text((x + 2, y + 2), t, font=fonts[w], fill=(0, 0, 0, 120))
        draw.text((x, y), t, font=fonts[w], fill=(255, 255, 255, 255))
        y += lh + gap
    img.save(path)
    return True


def make_endcard(job: VideoJob, path: Path) -> None:
    W, H = job.size
    u = min(W, H)
    base = np.array(hex_rgb(job.brand_color), np.float32)
    # Subtle vertical gradient from the brand colour.
    t = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    arr = base * (1.15 - 0.35 * t)
    img = Image.fromarray(np.clip(np.broadcast_to(arr, (H, W, 3)), 0, 255).astype(np.uint8)).convert("RGBA")
    draw = ImageDraw.Draw(img)

    blocks: list[tuple[str, Image.Image | tuple[str, str, int]]] = []
    if job.logo and job.logo.exists():
        logo = ImageOps.exif_transpose(Image.open(job.logo)).convert("RGBA")
        logo.thumbnail((int(W * 0.5), int(u * 0.28)), Image.LANCZOS)
        blocks.append(("img", logo))
    if job.broker_name:
        blocks.append(("txt", ("bold", job.broker_name, int(u * 0.07))))
    if job.phone:
        blocks.append(("txt", ("regular", job.phone, int(u * 0.05))))
    if job.tagline:
        blocks.append(("txt", ("regular", job.tagline, int(u * 0.034))))

    rendered = []
    for kind, b in blocks:
        if kind == "img":
            rendered.append((b, b.size[1]))
        else:
            weight, text, size = b
            font = load_font(job, weight, size)
            bb = draw.textbbox((0, 0), text, font=font)
            rendered.append(((text, font, bb), bb[3]))
    gap = int(u * 0.035)
    y = (H - sum(h for _, h in rendered) - gap * max(len(rendered) - 1, 0)) // 2
    for item, h in rendered:
        if isinstance(item, Image.Image):
            img.alpha_composite(item, ((W - item.size[0]) // 2, y))
        else:
            text, font, bb = item
            draw.text(((W - (bb[2] - bb[0])) // 2 - bb[0], y), text, font=font, fill=(255, 255, 255))
        y += h + gap
    img.convert("RGB").save(path)


# --------------------------------------------------------------------------- #
# 5. FFmpeg
# --------------------------------------------------------------------------- #

def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("FFmpeg not found. Install it (or `pip install imageio-ffmpeg`) and retry.")


class ClipWriter:
    """Pipes raw BGR frames into FFmpeg -> near-lossless intermediate H.264."""

    def __init__(self, path: Path, job: VideoJob):
        W, H = job.size
        self.proc = subprocess.Popen(
            [ffmpeg_exe(), "-y", "-loglevel", "error",
             "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(job.fps),
             "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12",
             "-pix_fmt", "yuv420p", str(path)],
            stdin=subprocess.PIPE,
        )

    def write(self, frame: np.ndarray) -> None:
        self.proc.stdin.write(np.ascontiguousarray(frame).tobytes())

    def close(self) -> None:
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise RuntimeError("FFmpeg failed while writing a clip")


def stitch(job: VideoJob, clips: list[Path], endcard: Path, overlay: Path | None) -> None:
    fps, xf = job.fps, job.crossfade
    durations = [job.clip_seconds] * len(clips) + [job.endcard_seconds]
    total = sum(durations) - xf * (len(durations) - 1)

    args = [ffmpeg_exe(), "-y", "-loglevel", "error"]
    for c in clips:
        args += ["-i", str(c)]
    args += ["-loop", "1", "-framerate", str(fps), "-t", f"{job.endcard_seconds}", "-i", str(endcard)]
    n_video = len(clips) + 1
    idx = n_video
    ov_idx = mus_idx = None
    if overlay:
        args += ["-loop", "1", "-framerate", str(fps), "-t", f"{total}", "-i", str(overlay)]
        ov_idx, idx = idx, idx + 1
    if job.music:
        args += ["-stream_loop", "-1", "-i", str(job.music)]
        mus_idx = idx

    f = []
    for i in range(n_video):
        f.append(f"[{i}:v]fps={fps},format=yuv420p,setsar=1,settb=AVTB[v{i}]")
    prev, offset = "v0", 0.0
    for i in range(1, n_video):
        offset += durations[i - 1] - xf
        out = f"x{i}"
        f.append(f"[{prev}][v{i}]xfade=transition=fade:duration={xf}:offset={offset:.3f}[{out}]")
        prev = out
    if ov_idx is not None:
        # Lower-third: fades in shortly after the start, out before the end card.
        endcard_start = total - job.endcard_seconds
        ov_out = max(1.0, endcard_start - 0.6)
        f.append(
            f"[{ov_idx}:v]format=rgba,"
            f"fade=t=in:st=0.6:d=0.7:alpha=1,fade=t=out:st={ov_out:.3f}:d=0.6:alpha=1[ov]"
        )
        f.append(f"[{prev}][ov]overlay=0:0:format=auto,format=yuv420p[vout]")
    else:
        f.append(f"[{prev}]format=yuv420p[vout]")
    maps = ["-map", "[vout]"]
    if mus_idx is not None:
        fade = min(job.music_fade, total / 2)
        f.append(
            f"[{mus_idx}:a]atrim=duration={total:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=0.5,afade=t=out:st={total - fade:.3f}:d={fade}[aout]"
        )
        maps += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]

    args += ["-filter_complex", ";".join(f), *maps,
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
             "-pix_fmt", "yuv420p", "-r", str(fps), "-t", f"{total:.3f}",
             "-movflags", "+faststart", str(job.out)]
    job.out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(args, check=True)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def pick_moves(job: VideoJob) -> list[str]:
    if job.moves != ["auto"]:
        return [job.moves[i % len(job.moves)] for i in range(len(job.photos))]
    cycle = (["push-right", "rise-push", "pull-left", "push-left", "orbit-right", "rise-push"]
             if job.aspect == "9:16"
             else ["push-right", "pull-left", "orbit-right", "push-left", "rise-push", "pull-right"])
    return [cycle[i % len(cycle)] for i in range(len(job.photos))]


def build_video(job: VideoJob, log: Callable[[str], None] = print) -> Path:
    t0 = time.time()
    moves = pick_moves(job)
    depth = DepthEstimator() if job.depth_mode == "model" else None
    # Supersample so zoomed frames stay sharp (push-ins reach ~1.3x).
    supersample = 1.5

    ctx = tempfile.TemporaryDirectory(prefix="glide_") if job.keep_work is None else None
    work = Path(ctx.name) if ctx else job.keep_work
    work.mkdir(parents=True, exist_ok=True)
    try:
        clips = []
        for i, (photo, move) in enumerate(zip(job.photos, moves)):
            t = time.time()
            src = prep_photo(photo, job, supersample)
            raw = depth(src) if depth else gradient_depth(src)
            disp = clean_disparity(raw)
            if job.keep_work:
                cv2.imwrite(str(work / f"depth_{i:02d}.png"),
                            cv2.applyColorMap((disp * 255).astype(np.uint8), cv2.COLORMAP_INFERNO))
            clip = work / f"clip_{i:02d}.mp4"
            writer = ClipWriter(clip, job)
            render_clip(src, disp, make_move(move, job.intensity), job, writer.write)
            writer.close()
            clips.append(clip)
            log(f"[{i + 1}/{len(job.photos)}] {photo.name}: {move} ({time.time() - t:.1f}s)")

        endcard = work / "endcard.png"
        make_endcard(job, endcard)
        overlay = work / "info.png"
        has_overlay = make_info_overlay(job, overlay)
        log("Stitching with FFmpeg...")
        stitch(job, clips, endcard, overlay if has_overlay else None)
    finally:
        if ctx:
            ctx.cleanup()
    log(f"Done: {job.out}  ({time.time() - t0:.0f}s total)")
    return job.out


def collect_photos(folder: Path, limit: int) -> list[Path]:
    photos = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not photos:
        sys.exit(f"No photos found in {folder}")
    return photos[:limit]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Turn listing photos into a parallax walkthrough video.")
    ap.add_argument("photos", type=Path, help="folder of photos (used in filename order)")
    ap.add_argument("-o", "--out", type=Path, default=Path("glide.mp4"))
    ap.add_argument("--aspect", choices=list(ASPECTS), default="16:9")
    ap.add_argument("--max-photos", type=int, default=6, help="6 photos x 5s + end card ~= 30s")
    ap.add_argument("--clip-seconds", type=float, default=5.0)
    ap.add_argument("--crossfade", type=float, default=0.8)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--moves", default="auto",
                    help=f"'auto' or comma list, cycled per photo: {','.join(MOVES)}")
    ap.add_argument("--intensity", type=float, default=1.0, help="motion strength, 0.5 subtle - 1.5 strong")
    ap.add_argument("--no-enhance", action="store_true", help="skip auto brightness/contrast")
    ap.add_argument("--depth", choices=["model", "gradient"], default="model",
                    help="'gradient' skips the AI model (fast pipeline test)")
    ap.add_argument("--draft", action="store_true", help="2/3 resolution for quick previews")
    ap.add_argument("--price")
    ap.add_argument("--beds")
    ap.add_argument("--baths")
    ap.add_argument("--area", help='e.g. "145 m\u00b2"')
    ap.add_argument("--location")
    ap.add_argument("--broker-name")
    ap.add_argument("--phone")
    ap.add_argument("--logo", type=Path)
    ap.add_argument("--tagline")
    ap.add_argument("--brand-color", default="#0f2a3a")
    ap.add_argument("--endcard-seconds", type=float, default=4.0)
    ap.add_argument("--music", type=Path)
    ap.add_argument("--music-fade", type=float, default=3.0)
    ap.add_argument("--font", type=Path, help="TTF/OTF to use instead of the system font")
    ap.add_argument("--keep-work", type=Path, help="keep intermediate clips + depth previews here")
    a = ap.parse_args(argv)

    moves = [m.strip() for m in a.moves.split(",")]
    bad = [m for m in moves if m != "auto" and m not in MOVES]
    if bad:
        ap.error(f"unknown move(s): {bad}. Choose from {MOVES}")

    job = VideoJob(
        photos=collect_photos(a.photos, a.max_photos), out=a.out, aspect=a.aspect,
        fps=a.fps, clip_seconds=a.clip_seconds, crossfade=a.crossfade, moves=moves,
        intensity=a.intensity, enhance=not a.no_enhance, depth_mode=a.depth, draft=a.draft,
        price=a.price, beds=a.beds, baths=a.baths, area=a.area, location=a.location,
        broker_name=a.broker_name, phone=a.phone, logo=a.logo, tagline=a.tagline,
        brand_color=a.brand_color, endcard_seconds=a.endcard_seconds,
        music=a.music, music_fade=a.music_fade, font=a.font, keep_work=a.keep_work,
    )
    build_video(job)


if __name__ == "__main__":
    main()
