"""Freeze the dashboard into one self-contained HTML file (data + screenshots embedded).
Usage: .venv/bin/python tools/snapshot.py out.html [--label "Demo"]
Reads from the same TICKER_TRACKER_HOME the server uses.
"""
import base64
import json
import mimetypes
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tracker import config, web  # noqa: E402

out = Path(sys.argv[1])
label = sys.argv[sys.argv.index("--label") + 1] if "--label" in sys.argv else "Snapshot"
data = web.build_payload()
for s in data["submissions"]:
    if s.get("screenshot"):
        f = config.SCREENSHOT_DIR / s["screenshot"]
        if f.exists():
            mt = mimetypes.guess_type(f.name)[0] or "image/jpeg"
            s["screenshot_data"] = f"data:{mt};base64," + base64.b64encode(f.read_bytes()).decode()
html = (Path(__file__).resolve().parents[1] / "tracker/static/index.html").read_text()
stamp = datetime.now().strftime("%b %d, %Y %I:%M %p")
html = html.replace('async function load() {\n  const r = await fetch("/api/data"); DATA = await r.json(); render();\n}',
                    'async function load() { DATA = window.__SNAPSHOT__; render(); }')
html = html.replace("load(); setInterval(load, 60000);", "load();")
html = html.replace('src="/screenshots/${esc(s.screenshot)}" data-src="/screenshots/${esc(s.screenshot)}"',
                    'src="${s.screenshot_data || ""}" data-src="${s.screenshot_data || ""}"')
html = html.replace('<button class="btn" id="refresh">Refresh prices</button>',
                    f'<span class="sub" style="color:var(--ink-3)">{label} · frozen {stamp}</span>')
import re
html = re.sub(r'document\.getElementById\("refresh"\)\.onclick = async e => \{.*?\};\n', '', html, count=1, flags=re.S)
html = html.replace('<style>', '<style>\n  .card .menu, .fix { display: none !important; }', 1)
html = html.replace('</head>', '<script>window.__SNAPSHOT__ = ' + json.dumps(data) + ';</script>\n</head>', 1)
out.write_text(html)
print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(data['submissions'])} ideas)")
