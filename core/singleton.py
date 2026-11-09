# -*- coding: utf-8 -*-
"""
单实例 + 后台唤醒机制。

程序关闭窗口后并不真正退出，而是隐藏到后台继续运行（不显示托盘图标）。
如果用户再次双击 exe，新进程会检测到已有实例在运行，通知旧实例把窗口显示出来，
然后新进程自己立即退出，这样永远只有一份界面。
"""
import socket
import threading

SINGLETON_PORT = 53218


class SingleInstance:
    def __init__(self, on_show=None):
        self.on_show = on_show
        self._sock = None

    def try_become_primary(self):
        """返回 True：本次启动是第一个实例，可以继续创建界面。
        返回 False：已有实例在后台运行，已经通知它显示窗口，本进程应立即退出。"""
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(1)
        try:
            client.connect(('127.0.0.1', SINGLETON_PORT))
            client.sendall(b'SHOW')
            return False
        except OSError:
            pass
        finally:
            try:
                client.close()
            except OSError:
                pass

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind(('127.0.0.1', SINGLETON_PORT))
            self._sock.listen(5)
        except OSError:
            return False  # 极端竞争情况，当成已有实例处理

        threading.Thread(target=self._listen, daemon=True).start()
        return True

    def _listen(self):
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                break
            try:
                data = conn.recv(16)
                if data == b'SHOW' and self.on_show:
                    self.on_show()
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
