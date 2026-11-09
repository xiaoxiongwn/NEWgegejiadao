# -*- coding: utf-8 -*-
"""
WebDAV 服务器核心模块。
密码保护说明：Windows 自带的 WebDAV 客户端（映射网络位置用的那个）默认不允许
在非 HTTPS 连接上发送 Basic Auth 密码，所以这里改用"路径暗号"的方式实现密码保护：
设置密码后，真正可访问的地址会变成 .../DavWWWRoot/你的密码/ 这样一段路径，
不知道这段路径的人访问不到任何内容，效果上等同于密码保护，且不受 Windows 限制。
"""
import datetime
import email.utils
import http.server
import os
import shutil
import socketserver
import threading
import urllib.parse
import uuid
import xml.sax.saxutils as sax

from core import storage

_locks = {}


def rfc1123(ts):
    return email.utils.formatdate(ts, usegmt=True)


def iso8601(ts):
    return datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%dT%H:%M:%SZ')


def make_handler(root, password):
    require_secret = bool(password)
    prefix = ('/' + urllib.parse.quote(password)) if require_secret else ''

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        server_version = 'GeGeJiaDao-WebDAV/1.0'

        def log_message(self, fmt, *args):
            try:
                storage.append_log('[WebDAV %s] %s' % (self.client_address[0], fmt % args))
            except Exception:
                pass

        def _strip_prefix(self, raw_path):
            p = raw_path.split('?')[0]
            if not require_secret:
                return p
            if p == prefix or p == prefix + '/':
                return '/'
            if p.startswith(prefix + '/'):
                return p[len(prefix):]
            return None

        def safe_path(self, url_path):
            stripped = self._strip_prefix(url_path)
            if stripped is None:
                return None
            rel = urllib.parse.unquote(stripped).lstrip('/')
            full = os.path.normpath(os.path.join(root, rel))
            root_norm = os.path.normpath(root)
            if full != root_norm and not full.startswith(root_norm + os.sep):
                return None
            return full

        def url_for(self, full_path):
            rel = os.path.relpath(full_path, root).replace('\\', '/')
            base = prefix if require_secret else ''
            if rel == '.':
                return base + '/' if base else '/'
            href = base + '/' + urllib.parse.quote(rel)
            if os.path.isdir(full_path):
                href += '/'
            return href

        def common_headers(self):
            self.send_header('DAV', '1,2')
            self.send_header('MS-Author-Via', 'DAV')

        def do_OPTIONS(self):
            self.send_response(200)
            self.common_headers()
            self.send_header('Allow', 'OPTIONS, GET, HEAD, PUT, DELETE, PROPFIND, PROPPATCH, MKCOL, COPY, MOVE, LOCK, UNLOCK')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def do_HEAD(self):
            self._send_file(send_body=False)

        def do_GET(self):
            self._send_file(send_body=True)

        def _send_file(self, send_body):
            full = self.safe_path(self.path)
            if full is None or not os.path.exists(full):
                self.send_error(404)
                return
            if os.path.isdir(full):
                names = sorted(os.listdir(full))
                html_body = '<html><body><h3>%s</h3><ul>%s</ul></body></html>' % (
                    sax.escape(full),
                    ''.join('<li><a href="%s">%s</a></li>' % (urllib.parse.quote(n), sax.escape(n)) for n in names))
                data = html_body.encode('utf-8')
                self.send_response(200)
                self.common_headers()
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                if send_body:
                    self.wfile.write(data)
                return
            size = os.path.getsize(full)
            self.send_response(200)
            self.common_headers()
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(size))
            self.send_header('Last-Modified', rfc1123(os.path.getmtime(full)))
            self.end_headers()
            if send_body:
                with open(full, 'rb') as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)

        def do_PUT(self):
            full = self.safe_path(self.path)
            if full is None:
                storage.append_log('[WebDAV %s] PUT 被拒绝（密码段不匹配或路径非法）: %s' % (self.client_address[0], self.path))
                self.send_error(403)
                return
            length = int(self.headers.get('Content-Length', 0) or 0)
            storage.append_log('[WebDAV %s] PUT 开始，目标: %s，期望字节数: %d' % (self.client_address[0], full, length))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            written = 0
            try:
                with open(full, 'wb') as f:
                    remaining = length
                    while remaining > 0:
                        chunk = self.rfile.read(min(65536, remaining))
                        if not chunk:
                            break
                        f.write(chunk)
                        written += len(chunk)
                        remaining -= len(chunk)
            except Exception as e:
                storage.append_log('[WebDAV %s] PUT 写入失败: %s' % (self.client_address[0], e))
                self.send_error(500, str(e))
                return
            storage.append_log('[WebDAV %s] PUT 完成，实际写入字节数: %d（%s）'
                                % (self.client_address[0], written,
                                   '正常' if written == length else '⚠不完整，可能被中断'))
            self.send_response(201)
            self.common_headers()
            self.send_header('Content-Length', '0')
            self.end_headers()

        def do_DELETE(self):
            full = self.safe_path(self.path)
            if full is None or not os.path.exists(full):
                self.send_error(404)
                return
            try:
                if os.path.isdir(full):
                    os.rmdir(full)
                else:
                    os.remove(full)
            except OSError as e:
                self.send_error(500, str(e))
                return
            self.send_response(204)
            self.common_headers()
            self.send_header('Content-Length', '0')
            self.end_headers()

        def do_MKCOL(self):
            full = self.safe_path(self.path)
            if full is None:
                self.send_error(403)
                return
            try:
                os.makedirs(full, exist_ok=False)
            except OSError as e:
                self.send_error(409, str(e))
                return
            self.send_response(201)
            self.common_headers()
            self.send_header('Content-Length', '0')
            self.end_headers()

        def do_MOVE(self):
            self._copy_or_move(move=True)

        def do_COPY(self):
            self._copy_or_move(move=False)

        def _copy_or_move(self, move):
            src = self.safe_path(self.path)
            dest_hdr = self.headers.get('Destination', '')
            dest_path = urllib.parse.urlparse(dest_hdr).path
            dst = self.safe_path(dest_path)
            if src is None or dst is None or not os.path.exists(src):
                self.send_error(404)
                return
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if move:
                    os.replace(src, dst)
                elif os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            except OSError as e:
                self.send_error(500, str(e))
                return
            self.send_response(201)
            self.common_headers()
            self.send_header('Content-Length', '0')
            self.end_headers()

        def do_PROPPATCH(self):
            full = self.safe_path(self.path)
            if full is None:
                self.send_error(404)
                return
            href = self.path.split('?')[0]
            body = ('<?xml version="1.0" encoding="utf-8"?>'
                    '<D:multistatus xmlns:D="DAV:">'
                    '<D:response><D:href>%s</D:href>'
                    '<D:propstat><D:prop/><D:status>HTTP/1.1 200 OK</D:status></D:propstat>'
                    '</D:response></D:multistatus>') % sax.escape(href)
            data = body.encode('utf-8')
            self.send_response(207)
            self.common_headers()
            self.send_header('Content-Type', 'text/xml; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_PROPFIND(self):
            full = self.safe_path(self.path)
            if full is None or not os.path.exists(full):
                self.send_error(404)
                return
            depth = self.headers.get('Depth', '1')
            length = int(self.headers.get('Content-Length', 0) or 0)
            if length:
                self.rfile.read(length)

            items = [full]
            if os.path.isdir(full) and depth != '0':
                try:
                    for name in sorted(os.listdir(full)):
                        items.append(os.path.join(full, name))
                except OSError:
                    pass

            responses = ''.join(self._propfind_entry(item) for item in items)
            body = ('<?xml version="1.0" encoding="utf-8"?>'
                    '<D:multistatus xmlns:D="DAV:">%s</D:multistatus>') % responses
            data = body.encode('utf-8')
            self.send_response(207)
            self.common_headers()
            self.send_header('Content-Type', 'text/xml; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _propfind_entry(self, full):
            is_dir = os.path.isdir(full)
            try:
                st = os.stat(full)
            except OSError:
                return ''
            href = self.url_for(full)
            name = os.path.basename(full) or '/'
            if is_dir:
                restype = '<D:resourcetype><D:collection/></D:resourcetype>'
                getlen = ''
            else:
                restype = '<D:resourcetype/>'
                getlen = '<D:getcontentlength>%d</D:getcontentlength>' % st.st_size
            prop = ('<D:displayname>%s</D:displayname>%s'
                    '<D:getlastmodified>%s</D:getlastmodified>'
                    '<D:creationdate>%s</D:creationdate>'
                    '<D:getcontenttype>application/octet-stream</D:getcontenttype>'
                    '%s') % (sax.escape(name), restype, rfc1123(st.st_mtime), iso8601(st.st_ctime), getlen)
            return ('<D:response><D:href>%s</D:href>'
                    '<D:propstat><D:prop>%s</D:prop>'
                    '<D:status>HTTP/1.1 200 OK</D:status></D:propstat>'
                    '</D:response>') % (sax.escape(href), prop)

        def do_LOCK(self):
            full = self.safe_path(self.path)
            if full is None:
                self.send_error(404)
                return
            # 如果客户端在 If 头里带了已有的锁token（说明是"续锁/重新确认锁"，
            # 常见于再次点击"保存"时），就原样返回同一把锁，而不是每次都发一把新的——
            # 发新锁会让 Windows 的 WebDAV 客户端认为旧锁状态对不上，从而导致原地保存失败。
            if_header = self.headers.get('If', '')
            existing = _locks.get(full)
            if existing and existing in if_header:
                token = existing
                storage.append_log('[WebDAV %s] LOCK 续锁: %s' % (self.client_address[0], full))
            else:
                token = 'opaquelocktoken:%s' % uuid.uuid4()
                storage.append_log('[WebDAV %s] LOCK 新建: %s' % (self.client_address[0], full))
            _locks[full] = token
            body = ('<?xml version="1.0" encoding="utf-8"?>'
                    '<D:prop xmlns:D="DAV:"><D:lockdiscovery><D:activelock>'
                    '<D:locktype><D:write/></D:locktype>'
                    '<D:lockscope><D:exclusive/></D:lockscope>'
                    '<D:depth>0</D:depth>'
                    '<D:timeout>Second-3600</D:timeout>'
                    '<D:locktoken><D:href>%s</D:href></D:locktoken>'
                    '</D:activelock></D:lockdiscovery></D:prop>') % token
            data = body.encode('utf-8')
            self.send_response(200)
            self.common_headers()
            self.send_header('Lock-Token', '<%s>' % token)
            self.send_header('Content-Type', 'text/xml; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_UNLOCK(self):
            full = self.safe_path(self.path)
            if full in _locks:
                del _locks[full]
                storage.append_log('[WebDAV %s] UNLOCK: %s' % (self.client_address[0], full))
            self.send_response(204)
            self.common_headers()
            self.send_header('Content-Length', '0')
            self.end_headers()

    return Handler


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class WebDAVServer:
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
