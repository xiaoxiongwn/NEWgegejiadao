# -*- coding: utf-8 -*-
import json
import socket
import threading

try:
    import winsound
except ImportError:
    winsound = None

NOTIFY_PORT = 53217


class NotifyService:
    def __init__(self, on_notify=None):
        """on_notify(sender_name, message) 会在收到提醒时被调用（运行在后台线程）"""
        self.on_notify = on_notify
        self._sock = None
        self._thread = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind(('0.0.0.0', NOTIFY_PORT))
        except OSError:
            self._sock = None
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _listen(self):
        while self._running:
            try:
                data, addr = self._sock.recvfrom(4096)
            except OSError:
                break
            try:
                payload = json.loads(data.decode('utf-8'))
                name = payload.get('from', '对方')
                msg = payload.get('msg', '给你发了一个文件，请查收')
            except Exception:
                name, msg = '对方', '给你发了一个文件，请查收'
            if winsound:
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    pass
            if self.on_notify:
                self.on_notify(name, msg)

    @staticmethod
    def send(ip, sender_name, msg, port=NOTIFY_PORT, timeout=2):
        payload = json.dumps({'from': sender_name, 'msg': msg}).encode('utf-8')
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        try:
            s.sendto(payload, (ip, port))
            return True
        except OSError:
            return False
        finally:
            s.close()
