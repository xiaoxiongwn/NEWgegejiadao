# -*- coding: utf-8 -*-
import socket


def get_local_ip():
    """获取本机局域网IP（不需要真正联网，只是用来确定路由）"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.168.1.1', 80))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return '127.0.0.1'
    finally:
        s.close()


def get_hostname():
    try:
        return socket.gethostname()
    except Exception:
        return '未知电脑'
