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
    bnd = b'--' + boundary.encode()
    parts = body.split(bnd)
    for part in parts:
        if b'Content-Disposition' not in part:
            continue
        header, sep, file_data = part.partition(b'\r\n\r\n')
        if not sep:
            continue
        if file_data.endswith(b'\r\n'):
            file_data = file_data[:-2]
        if file_data.endswith(b'--'):
            file_data = file_data[:-2]
        if file_data.endswith(b'\r\n'):
            file_data = file_data[:-2]
        m = re.search(rb'filename="([^"]+)"', header)
        if m:
            return m.group(1).decode(), file_data
    return None, None

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith('.xlsx')]) if os.path.exists(DATA_DIR) else []
        flist = ', '.join(files) if files else 'none'
        html = '<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
        html += 'body{font-family:Arial,sans-serif;margin:20px;background:#f8f9fa}'
        html += 'h3{color:#1f77b4;margin:0 0 12px}'
        html += 'input{margin-bottom:8px}button{background:#1f77b4;color:#fff;border:none;padding:8px 20px;border-radius:4px;cursor:pointer;font-size:14px}'
        html += 'button:hover{background:#166bb5}'
        html += '.ok{color:green;font-weight:bold}.err{color:red}'
        html += '.files{font-size:13px;color:#666;margin-top:12px}'
        html += '</style></head><body>'
        html += '<h3>Upload Excel (.xlsx)</h3>'
        html += '<form method="post" action="/upload" enctype="multipart/form-data">'
        html += '<input type="file" name="file" accept=".xlsx" required><br><br>'
        html += '<button type="submit">Upload &amp; Import</button></form>'
        html += '<div class="files">Files: ' + flist + '</div>'
        html += '<p><a href="/">Back to Screener</a></p>'
        html += '</body></html>'
        self.wfile.write(html.encode('utf-8'))

    def do_POST(self):
        if self.path != '/upload':
            self.send_error(404); return
        ctype = self.headers.get('Content-Type', '')
        clength = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(clength)
        m = re.search(r'boundary=([\w-]+)', ctype)
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
        msg = 'Imported ' + str(result) + ' records' if ok else 'Error: ' + str(result)
        self._respond(msg, ok)

    def _respond(self, msg, ok):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        cls = 'ok' if ok else 'err'
        html = '<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
        html += 'body{font-family:Arial,sans-serif;margin:20px}'
        html += '.ok{color:green}.err{color:red}'
        html += '</style></head><body>'
        html += '<h3 class="' + cls + '">' + msg + '</h3>'
        html += '<a href="/upload-page">Upload another</a> | '
        html += '<a href="/">Back to Screener</a>'
        html += '</body></html>'
        self.wfile.write(html.encode('utf-8'))

if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    HTTPServer(('0.0.0.0', 8502), Handler).serve_forever()
