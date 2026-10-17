"""Minimaler Ersatz für die GitHub-API im Deploy-Test: liefert Release- und CI-Läufe aus einer Zustandsdatei."""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

STATE = sys.argv[2]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        st = json.load(open(STATE))
        u = urlparse(self.path); q = parse_qs(u.query)
        if self.headers.get('Authorization') != 'Bearer test-token':
            self.send_response(401); self.end_headers(); return
        if u.path.endswith('/actions/workflows/release.yml/runs'):
            runs = [{'id': 1, 'head_sha': st['release'], 'head_branch': st.get('release_branch', 'main'), 'path': '.github/workflows/release.yml',
                     'event': 'workflow_dispatch', 'conclusion': 'success'}] if st.get('release') else []
        elif u.path.endswith('/actions/workflows/ci.yml/runs'):
            sha = q.get('head_sha', [''])[0]
            runs = [{'id': 2, 'head_sha': sha, 'head_branch': 'main', 'event': 'push', 'conclusion': 'success'}] if sha in st.get('ci_ok', []) else []
        else:
            self.send_response(404); self.end_headers(); return
        body = json.dumps({'total_count': len(runs), 'workflow_runs': runs}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(body)


HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()
