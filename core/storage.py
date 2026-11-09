# -*- coding: utf-8 -*-
import datetime
import json
import os
import threading

from core.network import get_hostname

_log_lock = threading.Lock()


def data_dir():
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    d = os.path.join(base, '格格驾到')
    os.makedirs(d, exist_ok=True)
    return d


CONTACTS_FILE = os.path.join(data_dir(), 'contacts.json')
SETTINGS_FILE = os.path.join(data_dir(), 'settings.json')
LOG_FILE = os.path.join(data_dir(), 'webdav.log')


def append_log(line):
    """把一条请求记录追加写入日志文件，方便排查"打开能行、保存不行"这类跨电脑问题"""
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with _log_lock:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write('[%s] %s\n' % (ts, line))
    except Exception:
        pass

DEFAULT_SETTINGS = {
    'nickname': get_hostname(),
    'folder': '',
    'webdav_port': 8765,
    'mobile_port': 8766,
    'password': '',
    'autostart': False,
    'minimize_to_tray': True,
}


def load_contacts():
    if not os.path.exists(CONTACTS_FILE):
        return []
    try:
        with open(CONTACTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def save_contacts(contacts):
    with open(CONTACTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(contacts, f, ensure_ascii=False, indent=2)


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings.update(json.load(f))
        except Exception:
            pass
    return settings


def save_settings(settings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
