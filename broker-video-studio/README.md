# Broker Video Studio: Glide (free CPU tier)

Turns listing photos into a ~30 s walkthrough video with a 3D parallax effect.
No GPU, no paid APIs. Depth comes from **Depth Anything V2 Small** (Apache-2.0)
run with ONNX Runtime. Do not switch to the Base/Large/Giant checkpoints: they
are CC-BY-NC (non-commercial).

## Setup (once)

```
pip install -r requirements.txt
```

The depth model (~99 MB) downloads to `models/` on first run.

## Run

Put photos in `photos/` (they're used in filename order, so name them `01.jpg`, `02.jpg`, ...).

```
python glide.py photos -o out/listing.mp4 --aspect 16:9 --price "$450,000 USD" --beds 2 --baths 2 --area "120 m²" --location "Aldea Zamá, Tulum" --broker-name "Jane Doe" --phone "+52 984 123 4567" --logo logo.png --tagline "Top Listings Riviera Maya" --music music.mp3
```

Useful flags:

| Flag | What it does |
|---|---|
| `--aspect 16:9 / 9:16 / 1:1` | 1920x1080 / 1080x1920 / 1080x1080 |
| `--draft` | 2/3 resolution, faster previews |
| `--moves auto` | or a comma list cycled per photo: `push-right,push-left,pull-right,pull-left,rise-push,orbit-right,orbit-left,push-in` |
| `--intensity 0.7` | calmer motion (1.0 default, 1.5 strong) |
| `--max-photos 6` | 6 x 5 s clips + 4 s end card, 0.8 s crossfades ≈ 30 s |
| `--no-enhance` | skip auto brightness/contrast (for already-edited photos) |
| `--depth gradient` | skip the AI model entirely (pipeline test only) |
| `--keep-work work` | keep the per-photo clips and coloured depth maps for debugging |
| `--brand-color "#0f2a3a"` | end-card background |

## For the later FastAPI / RQ work

`build_video(VideoJob(...))` is the entry point; the CLI is a thin wrapper around it.
An RQ worker can import `glide` and enqueue `build_video` directly.
