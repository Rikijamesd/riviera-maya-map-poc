import csv
import os

DIR = os.path.dirname(os.path.abspath(__file__))

STYLE = """
:root{
  --bg:#F6F3EC;
  --surface:#FFFFFF;
  --surface-2:#FBF9F4;
  --ink:#16211F;
  --muted:#6E7570;
  --accent:#1B7A74;
  --accent-strong:#125C57;
  --accent-ink:#FFFFFF;
  --data:#C9603D;
  --border:#E4DFD2;
  --shadow:0 1px 2px rgba(22,33,31,0.06),0 8px 24px -12px rgba(22,33,31,0.18);
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#0F1917;
    --surface:#16221F;
    --surface-2:#132019;
    --ink:#E9EFEC;
    --muted:#93A199;
    --accent:#35B0A8;
    --accent-strong:#4FCFC6;
    --accent-ink:#06110F;
    --data:#E08862;
    --border:#24322E;
    --shadow:0 1px 2px rgba(0,0,0,0.3),0 12px 32px -16px rgba(0,0,0,0.55);
  }
}
:root[data-theme="dark"]{
  --bg:#0F1917;--surface:#16221F;--surface-2:#132019;--ink:#E9EFEC;--muted:#93A199;
  --accent:#35B0A8;--accent-strong:#4FCFC6;--accent-ink:#06110F;--data:#E08862;--border:#24322E;
  --shadow:0 1px 2px rgba(0,0,0,0.3),0 12px 32px -16px rgba(0,0,0,0.55);
}
:root[data-theme="light"]{
  --bg:#F6F3EC;--surface:#FFFFFF;--surface-2:#FBF9F4;--ink:#16211F;--muted:#6E7570;
  --accent:#1B7A74;--accent-strong:#125C57;--accent-ink:#FFFFFF;--data:#C9603D;--border:#E4DFD2;
  --shadow:0 1px 2px rgba(22,33,31,0.06),0 8px 24px -12px rgba(22,33,31,0.18);
}
*{box-sizing:border-box;}
body{
  margin:0;
  min-height:100vh;
  display:flex;
  align-items:center;
  justify-content:center;
  padding:48px 20px;
  background:var(--bg);
  color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
}
.card{
  width:100%;
  max-width:560px;
  background:var(--surface);
  border:1px solid var(--border);
  border-radius:14px;
  box-shadow:var(--shadow);
  padding:36px 36px 32px;
}
.eyebrow{
  font-size:11px;
  font-weight:700;
  letter-spacing:0.11em;
  text-transform:uppercase;
  color:var(--accent);
  margin:0 0 14px;
}
h1{
  font-family:ui-monospace,"SF Mono",Consolas,Menlo,monospace;
  font-size:19px;
  font-weight:600;
  line-height:1.4;
  margin:0 0 10px;
  word-break:break-word;
  text-wrap:balance;
}
.desc{
  font-size:14.5px;
  line-height:1.55;
  color:var(--muted);
  margin:0 0 26px;
  max-width:52ch;
}
.stats{
  display:grid;
  grid-template-columns:repeat(3,1fr);
  gap:1px;
  background:var(--border);
  border:1px solid var(--border);
  border-radius:10px;
  overflow:hidden;
  margin-bottom:26px;
}
.stat{
  background:var(--surface-2);
  padding:14px 12px;
  text-align:center;
}
.stat .n{
  display:block;
  font-family:ui-monospace,"SF Mono",Consolas,Menlo,monospace;
  font-variant-numeric:tabular-nums;
  font-size:17px;
  font-weight:600;
  color:var(--data);
}
.stat .l{
  display:block;
  margin-top:3px;
  font-size:10.5px;
  letter-spacing:0.06em;
  text-transform:uppercase;
  color:var(--muted);
}
button.dl{
  width:100%;
  border:none;
  border-radius:9px;
  padding:14px 18px;
  font-size:15px;
  font-weight:600;
  font-family:inherit;
  background:var(--accent);
  color:var(--accent-ink);
  cursor:pointer;
  transition:background .15s ease, transform .05s ease;
}
button.dl:hover{background:var(--accent-strong);}
button.dl:active{transform:translateY(1px);}
button.dl:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}
.status{
  min-height:18px;
  margin-top:10px;
  font-size:12.5px;
  color:var(--muted);
  text-align:center;
}
.note{
  margin-top:22px;
  padding:12px 14px;
  border-left:3px solid var(--data);
  background:var(--surface-2);
  border-radius:0 8px 8px 0;
  font-size:12.5px;
  line-height:1.55;
  color:var(--muted);
}
.note b{color:var(--ink);}
"""

TEMPLATE = """<div class="card">
  <p class="eyebrow">AirROI &middot; Tulum STR Export</p>
  <h1>{filename}</h1>
  <p class="desc">{description}</p>
  <div class="stats">
    <div class="stat"><span class="n">{rows}</span><span class="l">Rows</span></div>
    <div class="stat"><span class="n">{cols}</span><span class="l">Columns</span></div>
    <div class="stat"><span class="n">{size}</span><span class="l">File size</span></div>
  </div>
  <button class="dl" id="dlBtn">Download {filename}</button>
  <p class="status" id="status"></p>
  <div class="note">{note}</div>
</div>
<textarea id="csvSource" style="position:absolute;left:-9999px;top:-9999px;" aria-hidden="true" tabindex="-1">{csv_content}</textarea>
<script>
document.getElementById('dlBtn').addEventListener('click', function () {{
  var status = document.getElementById('status');
  try {{
    var text = document.getElementById('csvSource').value;
    var blob = new Blob([text], {{ type: 'text/csv;charset=utf-8' }});
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = '{filename}';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    status.textContent = 'Download started.';
  }} catch (err) {{
    status.textContent = 'Download failed: ' + err.message;
  }}
}});
</script>
"""

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;")

def build(csv_name, out_name, description, note):
    path = os.path.join(DIR, csv_name)
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = sum(1 for _ in reader)
    cols = len(header)
    size_bytes = os.path.getsize(path)
    size_mb = f"{size_bytes/1024/1024:.1f} MB"

    with open(path, encoding="utf-8-sig") as f:
        raw = f.read()
    csv_escaped = esc(raw)

    html = f"<style>{STYLE}</style>\n" + TEMPLATE.format(
        filename=csv_name,
        description=description,
        rows=f"{rows:,}",
        cols=cols,
        size=size_mb,
        note=note,
        csv_content=csv_escaped,
    )
    out_path = os.path.join(DIR, out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote", out_path, os.path.getsize(out_path))

build(
    "airroi_properties.csv",
    "download_properties.html",
    "One row per Tulum short-term rental listing — location, host, room specs, ratings, amenities, plus trailing-12-month and last-90-day performance metrics.",
    "<b>Currency note:</b> rate and revenue fields are Mexican pesos (MXN), despite some source field names ending in “_usd.” Confirmed against studio-unit nightly rates, which only make sense in MXN.",
)

build(
    "airroi_monthly_metrics.csv",
    "download_monthly_metrics.html",
    "Long-format monthly time series — one row per property per month, with occupancy, ADR, RevPAR, and revenue. Built for seasonality charts and trend lines.",
    "<b>Currency note:</b> same MXN caveat as the properties file — the “_usd” suffix in the source column names is a mislabel. This file has more rows than the properties file; if your spreadsheet app struggles to open it, that row count is the likely reason.",
)
