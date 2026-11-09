# -*- coding: utf-8 -*-
import base64
import html
import http.server
import mimetypes
import os
import socketserver
import threading
import urllib.parse


def make_handler(root, password):
    auth_required = bool(password)

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = 'GeGeJiaDao-Mobile/1.0'

        def log_message(self, fmt, *args):
            pass

        def _check_auth(self):
            if not auth_required:
                return True
            got = self.headers.get('Authorization', '')
            if got.startswith('Basic '):
                try:
                    decoded = base64.b64decode(got[6:]).decode('utf-8', 'ignore')
                    _, _, pwd = decoded.partition(':')
                    if pwd == password:
                        return True
                except Exception:
                    pass
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="GeGeJiaDao"')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return False

        def safe_path(self, rel_path):
            rel_path = rel_path.lstrip('/')
            full = os.path.normpath(os.path.join(root, urllib.parse.unquote(rel_path)))
            if not full.startswith(os.path.normpath(root)):
                return None
            return full

        def do_GET(self):
            if not self._check_auth():
                return
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == '/download':
                self._download(parsed)
            else:
                self._list(parsed)

        def do_POST(self):
            if not self._check_auth():
                return
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == '/upload':
                self._upload(parsed)
            else:
                self.send_error(404)

        def _list(self, parsed):
            qs = urllib.parse.parse_qs(parsed.query)
            rel = qs.get('path', [''])[0]
            full = self.safe_path(rel)
            if full is None or not os.path.isdir(full):
                self.send_error(403)
                return
            entries = sorted(os.listdir(full), key=lambda n: (not os.path.isdir(os.path.join(full, n)), n.lower()))
            rows = ''
            if rel:
                parent = rel.rstrip('/').rsplit('/', 1)[0] if '/' in rel.rstrip('/') else ''
                rows += '<tr><td colspan="2"><a href="/?path=%s">⬆ 上级目录</a></td></tr>' % urllib.parse.quote(parent)
            for name in entries:
                entry_full = os.path.join(full, name)
                entry_rel = (rel.rstrip('/') + '/' + name) if rel else name
                if os.path.isdir(entry_full):
                    rows += '<tr><td>📁 <a href="/?path=%s">%s</a></td><td></td></tr>' % (
                        urllib.parse.quote(entry_rel), html.escape(name))
                else:
                    size = os.path.getsize(entry_full)
                    size_str = '%.1f KB' % (size / 1024) if size < 1024 * 1024 else '%.1f MB' % (size / 1024 / 1024)
                    rows += '<tr><td>📄 %s</td><td><a href="/download?path=%s">下载</a>（%s）</td></tr>' % (
                        html.escape(name), urllib.parse.quote(entry_rel), size_str)
            page = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>格格驾到</title>
<style>
body{font-family:-apple-system,Microsoft YaHei,Arial,sans-serif;margin:16px;background:#f7f7fb;}
h2{font-size:16px;color:#333;}
table{border-collapse:collapse;width:100%%;background:#fff;border-radius:8px;overflow:hidden;}
td{padding:10px;border-bottom:1px solid #eee;}
a{color:#6c5ce7;text-decoration:none;}
form{margin-top:16px;padding:14px;background:#fff;border-radius:8px;}
input[type=submit]{background:#6c5ce7;color:#fff;border:none;padding:8px 16px;border-radius:6px;}
</style></head>
<body>
<h2>📂 当前目录: /%s</h2>
<table>%s</table>
<form action="/upload?path=%s" method="post" enctype="multipart/form-data">
  <b>上传文件：</b><br><br>
  <input type="file" name="file">
  <input type="submit" value="上传">
</form>
</body></html>""" % (html.escape(rel), rows, urllib.parse.quote(rel))
            data = page.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _download(self, parsed):
            qs = urllib.parse.parse_qs(parsed.query)
            rel = qs.get('path', [''])[0]
            full = self.safe_path(rel)
            if full is None or not os.path.isfile(full):
                self.send_error(404)
                return
            ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Disposition', 'attachment; filename="%s"' % urllib.parse.quote(os.path.basename(full)))
            self.send_header('Content-Length', str(os.path.getsize(full)))
            self.end_headers()
            with open(full, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

        def _upload(self, parsed):
            qs = urllib.parse.parse_qs(parsed.query)
            rel = qs.get('path', [''])[0]
            target_dir = self.safe_path(rel)
            if target_dir is None or not os.path.isdir(target_dir):
                self.send_error(403)
                return
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type or 'boundary=' not in content_type:
                self.send_error(400)
                return
            boundary = content_type.split('boundary=')[1].strip().encode()
            length = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(length)
            for part in data.split(b'--' + boundary):
                if b'filename="' in part:
                    header, _, content = part.partition(b'\r\n\r\n')
                    if content.endswith(b'\r\n'):
                        content = content[:-2]
                    filename = header.split(b'filename="')[1].split(b'"')[0].decode('utf-8', 'ignore')
                    if filename:
                        out_path = os.path.join(target_dir, os.path.basename(filename))
                        with open(out_path, 'wb') as f:
                            f.write(content)
            self.send_response(303)
            self.send_header('Location', '/?path=%s' % urllib.parse.quote(rel))
            self.end_headers()

    return Handler


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class MobileServer:
    def __init__(self, folder, port, password=''):
        self.folder = folder
        self.port = port
        self.password = password
        self._httpd = None
        self._thread = None

    @property
    def running(self):
        return self._httpd is not None

    def start(self):
        if self.running:
            return
        handler = make_handler(self.folder, self.password)
        self._httpd = ThreadingHTTPServer(('0.0.0.0', self.port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
            self._thread = None
