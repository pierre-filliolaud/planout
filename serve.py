#!/usr/bin/env python3
"""
PlanOut local server
Serves all static files + generates data/index.json dynamically
from the actual contents of the data/ directory.
"""
import json, os, re
from http.server import HTTPServer, SimpleHTTPRequestHandler

ROOT     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, 'data')
PORT     = 3000

MONTH_NAMES = {
    '01':'January','02':'February','03':'March','04':'April',
    '05':'May','06':'June','07':'July','08':'August',
    '09':'September','10':'October','11':'November','12':'December',
}

def detect_theme(filename):
    n = filename.lower()
    # Full skill-name patterns (e.g. sorties-theatre, soirees-concert)
    if 'sorties-theatre' in n or 'theatre' in n: return 'spectacle'
    if 'sorties-musee'   in n or 'musee'   in n: return 'musee'
    if 'sorties-paris'   in n or 'paris'   in n: return 'paris'
    if 'soirees-techno'  in n or 'techno'  in n: return 'techno'
    if 'soirees-concert' in n or 'concert' in n: return 'concert'
    if 'sport-running'   in n or 'running' in n: return 'running'
    if 'sport-volley'    in n or 'volley'  in n: return 'volley'
    if 'spectacle' in n or 'show' in n:          return 'spectacle'
    return 'autre'

THEME_LABELS = {
    'musee':'Museums', 'paris':'Paris', 'techno':'Techno',
    'running':'Running', 'volley':'Volley', 'spectacle':'Shows',
    'concert':'Concerts', 'autre':'Other',
}

def build_index():
    try:
        entries = sorted(
            f for f in os.listdir(DATA_DIR)
            if f.endswith('.json') and f != 'index.json'
        )
    except FileNotFoundError:
        return {"files": []}

    files = []
    for f in entries:
        m     = re.match(r'^(\d{4}-(\d{2}))-(.+)\.json$', f)
        month = m.group(1) if m else ''
        mon   = MONTH_NAMES.get(m.group(2), '') if m else ''
        theme = detect_theme(f)
        label = (f"{mon} · {THEME_LABELS.get(theme, theme.title())}"
                 if mon else THEME_LABELS.get(theme, f))
        files.append({"file": f, "label": label, "theme": theme, "month": month})

    return {"files": files}


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        # Serve index.json dynamically — no static file needed
        if self.path in ('/data/index.json', '/data/index.json?'):
            body = json.dumps(build_index(), ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def log_message(self, fmt, *args):
        # Only log errors
        if args and isinstance(args[1], str) and not args[1].startswith('2'):
            super().log_message(fmt, *args)


if __name__ == '__main__':
    os.chdir(ROOT)
    # Write static data/index.json so GitHub Pages stays in sync
    idx_path = os.path.join(DATA_DIR, 'index.json')
    with open(idx_path, 'w', encoding='utf-8') as f:
        json.dump(build_index(), f, ensure_ascii=False, indent=2)
    print(f'data/index.json updated ({len(build_index()["files"])} files)')
    print(f'PlanOut → http://localhost:{PORT}')
    os.system(f'open http://localhost:{PORT}')
    HTTPServer(('', PORT), Handler).serve_forever()
