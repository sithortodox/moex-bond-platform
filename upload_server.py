#!/usr/bin/env python3
import os, sys, io, re
from http.server import HTTPServer, BaseHTTPRequestHandler

DATA_DIR = '/app/data'

def do_import(filepath):
    sys.path.insert(0, '/app')
    from data_collector import import_excel_data
    try:
        count = import_excel_data(filepath)
        return True, count
    except Exception as e:
        return False, str(e)

def parse_multipart(body, boundary):
    parts = body.split(b'--' + boundary.encode())
    for part in parts:
        if b'Content-Disposition' not in part:
            continue
        header, _, file_data = part.partition(b'\r\n\r\n')
        file_data = file_data.rstrip(b'\r\n')
        if file_data.endswith(b'--'):
            file_data = file_data[:-2].rstrip(b'\r\n')
        m = re.search(rb'filename="([^"]+)"', header)
        if m:
            return m.group(1).decode(), file_data
    return None, None

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Security-Policy', "frame-ancestors *")
        self.end_headers()
        files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith('.xlsx')]) if os.path.exists(DATA_DIR) else []
        flist = ', '.join(files) if files else ''
        html = '''<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;font-size:14px;color:#262730;background:transparent}
.row{display:flex;align-items:center;gap:8px;padding:4px 0}
input[type=file]{font-size:13px}
button{background:#1f77b4;color:#fff;border:none;padding:5px 14px;border-radius:4px;cursor:pointer;font-size:13px}
button:hover{background:#166bb5}
.msg{font-size:13px;margin-top:4px}
.ok{color:#21c35e}.err{color:#ea4335}
.files{font-size:12px;color:#888;margin-top:4px}
</style></head><body>
<form method="post" action="/upload" enctype="multipart/form-data" class="row">
<input type="file" name="file" accept=".xlsx" required>
<button type="submit">Upload & Import</button>
</form>
<div class="files">{flist}</div>
</body></html>'''.format(flist=flist)
        self.wfile.write(html.encode('utf-8'))

    def do_POST(self):
        if self.path != '/upload':
            self.send_error(404); return
        ctype = self.headers.get('Content-Type', '')
        clength = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(clength)
        m = re.search(r'boundary=(.+)', ctype)
        if not m:
            self._respond('Bad request', False); return
        boundary = m.group(1).strip()
        filename, file_data = parse_multipart(body, boundary)
        if not filename or not file_data:
            self._respond('No file found', False); return
        filepath = os.path.join(DATA_DIR, filename)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(file_data)
        ok, result = do_import(filepath)
        msg = 'Imported {} records'.format(result) if ok else 'Error: {}'.format(result)
        self._respond(msg, ok)

    def _respond(self, msg, ok):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Security-Policy', "frame-ancestors *")
        self.end_headers()
        cls = 'ok' if ok else 'err'
        files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith('.xlsx')]) if os.path.exists(DATA_DIR) else []
        flist = ', '.join(files) if files else ''
        html = '''<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;font-size:14px;color:#262730;background:transparent}
.msg{font-size:13px;margin:4px 0}
.ok{color:#21c35e}.err{color:#ea4335}
a{color:#1f77b4;font-size:13px}
.files{font-size:12px;color:#888;margin-top:4px}
</style></head><body>
<div class="msg {cls}">{msg}</div>
<a href="/">Upload another</a>
<div class="files">{flist}</div>
</body></html>'''.format(cls=cls, msg=msg, flist=flist)
        self.wfile.write(html.encode('utf-8'))

if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    HTTPServer(('0.0.0.0', 8502), Handler).serve_forever()
