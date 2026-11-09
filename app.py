# -*- coding: utf-8 -*-
"""
格格驾到 - 局域网文件直传/直编工具
"""
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core import autostart, storage, winflash
from core.mobile_server import MobileServer
from core.network import get_local_ip
from core.notify import NotifyService
from core.qr import make_qr_image
from core.singleton import SingleInstance
from core.webdav_server import WebDAVServer

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

ACCENT = "#6c5ce7"
ACCENT_HOVER = "#5a4bd1"
# PyInstaller 单文件模式运行时，附带资源会被解压到 sys._MEIPASS 临时目录
BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("格格驾到")
        self.geometry("920x600")
        self.minsize(820, 560)

        self.settings = storage.load_settings()
        self.contacts = storage.load_contacts()

        self.webdav = None
        self.mobile = None
        self.notify_service = NotifyService(on_notify=self._on_notify_received)
        self.notify_service.start()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- UI ----------------
    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color=ACCENT, height=64, corner_radius=0)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="👑 格格驾到", font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="white").pack(side="left", padx=24)
        ctk.CTkLabel(header, text="局域网文件直传 · 直接编辑", font=ctk.CTkFont(size=13),
                     text_color="#e8e4ff").pack(side="left")

        self.tabs = ctk.CTkTabview(self, fg_color="white", segmented_button_selected_color=ACCENT,
                                    segmented_button_selected_hover_color=ACCENT_HOVER)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=16)
        self.tab_share = self.tabs.add("📤 我的共享")
        self.tab_contacts = self.tabs.add("👥 同事地址簿")
        self.tab_settings = self.tabs.add("⚙ 设置")

        self._build_share_tab()
        self._build_contacts_tab()
        self._build_settings_tab()

    # ---------- 我的共享 ----------
    def _build_share_tab(self):
        left = ctk.CTkFrame(self.tab_share, fg_color="#f7f7fb", corner_radius=12)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=10)

        ctk.CTkLabel(left, text="共享文件夹", font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=20, pady=(20, 6))
        row = ctk.CTkFrame(left, fg_color="transparent")
        row.pack(fill="x", padx=20)
        self.folder_entry = ctk.CTkEntry(row, placeholder_text="选择要共享的文件夹...")
        self.folder_entry.pack(side="left", fill="x", expand=True)
        self.folder_entry.insert(0, self.settings.get('folder', ''))
        ctk.CTkButton(row, text="浏览", width=70, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._choose_folder).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(left, text="访问密码（留空则不设密码）", font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=20, pady=(16, 6))
        self.password_entry = ctk.CTkEntry(left, placeholder_text="留空 = 任何人都能访问", show="●")
        self.password_entry.pack(fill="x", padx=20)
        self.password_entry.insert(0, self.settings.get('password', ''))

        port_row = ctk.CTkFrame(left, fg_color="transparent")
        port_row.pack(fill="x", padx=20, pady=(16, 0))
        ctk.CTkLabel(port_row, text="电脑端口").pack(side="left")
        self.webdav_port_entry = ctk.CTkEntry(port_row, width=80)
        self.webdav_port_entry.insert(0, str(self.settings.get('webdav_port', 8765)))
        self.webdav_port_entry.pack(side="left", padx=(8, 20))
        ctk.CTkLabel(port_row, text="手机端口").pack(side="left")
        self.mobile_port_entry = ctk.CTkEntry(port_row, width=80)
        self.mobile_port_entry.insert(0, str(self.settings.get('mobile_port', 8766)))
        self.mobile_port_entry.pack(side="left", padx=(8, 0))

        self.toggle_btn = ctk.CTkButton(left, text="▶ 开始共享", height=42, fg_color=ACCENT,
                                         hover_color=ACCENT_HOVER, font=ctk.CTkFont(size=15, weight="bold"),
                                         command=self._toggle_share)
        self.toggle_btn.pack(fill="x", padx=20, pady=(24, 10))

        self.status_label = ctk.CTkLabel(left, text="● 未共享", text_color="#999", anchor="w")
        self.status_label.pack(fill="x", padx=20)

        info_box = ctk.CTkFrame(left, fg_color="white", corner_radius=10)
        info_box.pack(fill="x", padx=20, pady=16)
        ctk.CTkLabel(info_box, text="电脑访问地址（在资源管理器地址栏粘贴）：",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", padx=14, pady=(12, 2))
        addr_row, self.webdav_addr_var = self._make_copyable_row(info_box, "--")
        addr_row.pack(fill="x", padx=14, pady=(0, 12))

        right = ctk.CTkFrame(self.tab_share, fg_color="#f7f7fb", corner_radius=12, width=260)
        right.pack(side="right", fill="y", pady=10)
        right.pack_propagate(False)
        ctk.CTkLabel(right, text="📱 手机扫码访问", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(20, 10))
        self.qr_label = ctk.CTkLabel(right, text="开始共享后显示二维码", width=200, height=200,
                                      fg_color="white", corner_radius=10)
        self.qr_label.pack(padx=20, pady=10)
        mobile_row, self.mobile_addr_var = self._make_copyable_row(right, "")
        mobile_row.pack(fill="x", padx=20, pady=(0, 6))
        self.mobile_hint_label = ctk.CTkLabel(right, text="", font=ctk.CTkFont(size=11), text_color="#999",
                                               wraplength=220)
        self.mobile_hint_label.pack(padx=20, pady=(0, 20))

    def _copy_to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    def _make_copyable_row(self, parent, initial_text="--"):
        """创建一个只读、但可以选中/一键复制的地址框，返回 (frame, entry) 以便后续更新内容"""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        entry_var = tk.StringVar(value=initial_text)
        entry = ctk.CTkEntry(row, textvariable=entry_var, font=ctk.CTkFont(size=13, weight="bold"))
        entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="复制", width=56, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=lambda: self._copy_to_clipboard(entry_var.get())).pack(side="left", padx=(6, 0))
        return row, entry_var

    def _show_copyable_dialog(self, title, hint, content):
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("460x160")
        dlg.grab_set()
        ctk.CTkLabel(dlg, text=hint, wraplength=420, justify="left").pack(anchor="w", padx=20, pady=(18, 8))
        var = tk.StringVar(value=content)
        entry = ctk.CTkEntry(dlg, textvariable=var, font=ctk.CTkFont(size=13, weight="bold"))
        entry.pack(fill="x", padx=20)
        entry.focus_set()
        entry.select_range(0, "end")
        ctk.CTkButton(dlg, text="复制地址", fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=lambda: self._copy_to_clipboard(var.get())).pack(fill="x", padx=20, pady=18)

    def _choose_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, path)

    def _toggle_share(self):
        if self.webdav and self.webdav.running:
            self._stop_share()
        else:
            self._start_share()

    def _start_share(self):
        folder = self.folder_entry.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("格格驾到", "请先选择一个有效的文件夹")
            return
        try:
            webdav_port = int(self.webdav_port_entry.get().strip())
            mobile_port = int(self.mobile_port_entry.get().strip())
        except ValueError:
            messagebox.showwarning("格格驾到", "端口必须是数字")
            return
        password = self.password_entry.get().strip()
        if password and not re.match(r'^[A-Za-z0-9_\-]+$', password):
            messagebox.showwarning("格格驾到", "密码会被当作地址的一部分，请只使用英文字母、数字、下划线或横线")
            return

        self.webdav = WebDAVServer(folder, webdav_port, password=password)
        self.mobile = MobileServer(folder, mobile_port, password=password)
        try:
            self.webdav.start()
            self.mobile.start()
        except OSError as e:
            messagebox.showerror("格格驾到", "启动失败，端口可能被占用：%s" % e)
            return

        ip = get_local_ip()
        if password:
            webdav_addr = "\\\\%s@%d\\DavWWWRoot\\%s\\" % (ip, webdav_port, password)
        else:
            webdav_addr = "\\\\%s@%d\\DavWWWRoot\\" % (ip, webdav_port)
        mobile_addr = "http://%s:%d" % (ip, mobile_port)
        self.webdav_addr_var.set(webdav_addr)
        self.mobile_addr_var.set(mobile_addr)
        self.mobile_hint_label.configure(
            text="手机浏览器打开后会要求输入密码（用户名随意填）" if password else "手机浏览器扫码后直接可用")
        self._show_qr(mobile_addr)

        self.toggle_btn.configure(text="■ 停止共享", fg_color="#e74c3c", hover_color="#c0392b")
        self.status_label.configure(text="● 共享中  " + folder, text_color="#2ecc71")

        self.settings.update({
            'folder': folder, 'password': password,
            'webdav_port': webdav_port, 'mobile_port': mobile_port,
        })
        storage.save_settings(self.settings)

    def _stop_share(self):
        if self.webdav:
            self.webdav.stop()
        if self.mobile:
            self.mobile.stop()
        self.toggle_btn.configure(text="▶ 开始共享", fg_color=ACCENT, hover_color=ACCENT_HOVER)
        self.status_label.configure(text="● 未共享", text_color="#999")
        self.webdav_addr_var.set("--")
        self.mobile_addr_var.set("")
        self.mobile_hint_label.configure(text="")
        self.qr_label.configure(image=None, text="开始共享后显示二维码")

    def _show_qr(self, url):
        img = make_qr_image(url, box_size=5)
        img = img.resize((200, 200))
        ctk_img = ctk.CTkImage(light_image=img, size=(200, 200))
        self.qr_label.configure(image=ctk_img, text="")
        self.qr_label.image = ctk_img

    # ---------- 同事地址簿 ----------
    def _build_contacts_tab(self):
        top = ctk.CTkFrame(self.tab_contacts, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(top, text="+ 添加同事", fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._add_contact_dialog).pack(side="left")

        self.contacts_frame = ctk.CTkScrollableFrame(self.tab_contacts, fg_color="#f7f7fb")
        self.contacts_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._refresh_contacts()

    def _refresh_contacts(self):
        for w in self.contacts_frame.winfo_children():
            w.destroy()
        if not self.contacts:
            ctk.CTkLabel(self.contacts_frame, text="还没有添加同事，点击上方“+ 添加同事”开始",
                         text_color="#999").pack(pady=30)
            return
        for idx, c in enumerate(self.contacts):
            self._render_contact_row(idx, c)

    def _render_contact_row(self, idx, c):
        row = ctk.CTkFrame(self.contacts_frame, fg_color="white", corner_radius=10)
        row.pack(fill="x", pady=6, padx=4)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=16, pady=12)
        ctk.CTkLabel(info, text=c.get('name', '未命名'), font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w")
        detail = "%s : %s" % (c.get('ip', ''), c.get('port', ''))
        if c.get('password'):
            detail += "  🔒已设密码"
        ctk.CTkLabel(info, text=detail, text_color="#888", font=ctk.CTkFont(size=12)).pack(anchor="w")

        btns = ctk.CTkFrame(row, fg_color="transparent")
        btns.pack(side="right", padx=12, pady=10)
        ctk.CTkButton(btns, text="打开", width=60, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=lambda c=c: self._open_contact(c)).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="🔔提醒TA", width=80, fg_color="#f39c12", hover_color="#d68910",
                      command=lambda c=c: self._notify_contact(c)).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="编辑", width=60, fg_color="#95a5a6", hover_color="#7f8c8d",
                      command=lambda i=idx, c=c: self._add_contact_dialog(edit_index=i, contact=c)).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="删除", width=60, fg_color="#e74c3c", hover_color="#c0392b",
                      command=lambda i=idx: self._delete_contact(i)).pack(side="left", padx=4)

    def _open_contact(self, c):
        ip, port = c.get('ip'), c.get('port')
        if not ip or not port:
            return
        pwd = (c.get('password') or '').strip()
        if pwd:
            path = "\\\\%s@%s\\DavWWWRoot\\%s\\" % (ip, port, pwd)
        else:
            path = "\\\\%s@%s\\DavWWWRoot\\" % (ip, port)
        try:
            os.startfile(path)
        except Exception:
            self._show_copyable_dialog(
                "手动打开",
                "没能自动打开，请复制下面的地址，手动粘贴到\n“文件资源管理器”的地址栏：",
                path)

    def _notify_contact(self, c):
        ip = c.get('ip')
        if not ip:
            return
        nickname = self.settings.get('nickname', '同事')
        ok = NotifyService.send(ip, nickname, "%s 给你发了一个文件，请查收～" % nickname)
        if ok:
            messagebox.showinfo("格格驾到", "已提醒 %s" % c.get('name', ip))
        else:
            messagebox.showwarning("格格驾到", "提醒发送失败，请确认对方也在运行格格驾到")

    def _delete_contact(self, idx):
        if messagebox.askyesno("格格驾到", "确定删除这位同事吗？"):
            del self.contacts[idx]
            storage.save_contacts(self.contacts)
            self._refresh_contacts()

    def _add_contact_dialog(self, edit_index=None, contact=None):
        dlg = ctk.CTkToplevel(self)
        dlg.title("编辑同事" if contact else "添加同事")
        dlg.geometry("360x320")
        dlg.grab_set()

        fields = {}
        for label, key, default in [
            ("姓名/备注", "name", ""), ("IP 地址", "ip", ""),
            ("WebDAV 端口（即对方“电脑端口”，默认8765）", "port", "8765"),
            ("密码（留空则不需要，对方若设置了需一致）", "password", ""),
        ]:
            ctk.CTkLabel(dlg, text=label, font=ctk.CTkFont(size=12)).pack(anchor="w", padx=20, pady=(14, 2))
            show = "●" if key == "password" else ""
            entry = ctk.CTkEntry(dlg, show=show)
            entry.pack(fill="x", padx=20)
            # 新增时端口预填默认值8765，避免用户漏填导致连不上；编辑时显示已保存的值
            if contact:
                entry.insert(0, str(contact.get(key, default)))
            elif key == "port":
                entry.insert(0, default)
            fields[key] = entry

        def save():
            name = fields['name'].get().strip()
            ip = fields['ip'].get().strip()
            port = fields['port'].get().strip()
            if not name or not ip or not port:
                messagebox.showwarning("格格驾到", "姓名、IP、端口 不能为空")
                return
            data = {'name': name, 'ip': ip, 'port': port, 'password': fields['password'].get().strip()}
            if edit_index is not None:
                self.contacts[edit_index] = data
            else:
                self.contacts.append(data)
            storage.save_contacts(self.contacts)
            self._refresh_contacts()
            dlg.destroy()

        ctk.CTkButton(dlg, text="保存", fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=save).pack(fill="x", padx=20, pady=24)

    # ---------- 设置 ----------
    def _build_settings_tab(self):
        box = ctk.CTkFrame(self.tab_settings, fg_color="#f7f7fb", corner_radius=12)
        box.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(box, text="我的昵称（提醒对方时显示）", font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=20, pady=(20, 6))
        self.nickname_entry = ctk.CTkEntry(box)
        self.nickname_entry.insert(0, self.settings.get('nickname', ''))
        self.nickname_entry.pack(fill="x", padx=20)

        self.autostart_var = tk.BooleanVar(value=autostart.is_enabled())
        ctk.CTkCheckBox(box, text="开机自动启动", variable=self.autostart_var,
                        fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        command=self._toggle_autostart).pack(anchor="w", padx=20, pady=(20, 6))

        ctk.CTkButton(box, text="保存昵称", fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._save_nickname).pack(anchor="w", padx=20, pady=(0, 10))

        tip = ("点击右上角关闭按钮不会真正退出程序，而是隐藏到后台继续共享（不会出现在系统托盘）。\n"
               "想重新打开窗口时，再双击一次“格格驾到.exe”（或桌面快捷方式）即可自动唤出，\n"
               "不会重复打开新窗口。")
        ctk.CTkLabel(box, text=tip, font=ctk.CTkFont(size=12), text_color="#777",
                     justify="left", wraplength=640).pack(anchor="w", padx=20, pady=(0, 16))

        ctk.CTkButton(box, text="彻底退出程序（停止所有共享）", fg_color="#e74c3c", hover_color="#c0392b",
                      command=self._confirm_quit).pack(anchor="w", padx=20, pady=(0, 10))

        ctk.CTkButton(box, text="📋 打开日志文件（排查连接/保存问题用）", fg_color="#95a5a6", hover_color="#7f8c8d",
                      command=self._open_log).pack(anchor="w", padx=20, pady=(0, 20))

        ctk.CTkLabel(self.tab_settings, text="格格驾到 v1.0  ·  局域网文件直传与直接编辑工具",
                     text_color="#999").pack(pady=20)

    def _save_nickname(self):
        self.settings['nickname'] = self.nickname_entry.get().strip() or get_local_ip()
        storage.save_settings(self.settings)
        messagebox.showinfo("格格驾到", "已保存")

    def _toggle_autostart(self):
        autostart.set_enabled(self.autostart_var.get())
        self.settings['autostart'] = self.autostart_var.get()
        storage.save_settings(self.settings)

    def _open_log(self):
        if not os.path.exists(storage.LOG_FILE):
            messagebox.showinfo("格格驾到", "还没有任何记录（可能从未共享过，或者还没人访问过）")
            return
        try:
            os.startfile(storage.LOG_FILE)
        except Exception as e:
            messagebox.showerror("格格驾到", "打开失败：%s\n\n日志文件位置：\n%s" % (e, storage.LOG_FILE))

    def _confirm_quit(self):
        if messagebox.askyesno("格格驾到", "确定要彻底退出吗？退出后共享和提醒功能都会停止。"):
            self._quit()

    # ---------- 通知 / 提醒 ----------
    def _on_notify_received(self, sender_name, msg):
        self.after(0, lambda: self._show_notify_popup(sender_name, msg))

    def _show_notify_popup(self, sender_name, msg):
        try:
            winflash.flash_window(self.winfo_id())
        except Exception:
            pass
        popup = ctk.CTkToplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        w, h = 300, 90
        sw, sh = popup.winfo_screenwidth(), popup.winfo_screenheight()
        popup.geometry("%dx%d+%d+%d" % (w, h, sw - w - 20, sh - h - 60))
        frame = ctk.CTkFrame(popup, fg_color=ACCENT, corner_radius=12)
        frame.pack(fill="both", expand=True)
        ctk.CTkLabel(frame, text="🔔 %s" % sender_name, font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="white").pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(frame, text=msg, text_color="white", wraplength=260).pack(anchor="w", padx=16)
        popup.after(4500, popup.destroy)
        self.deiconify()
        self.lift()

    # ---------- 关闭 / 隐藏到后台 ----------
    def _on_close(self):
        # 点击关闭按钮：不退出，只是隐藏窗口（不显示任何托盘图标），
        # 共享、手机访问、提醒监听都继续在后台运行。
        self.withdraw()

    def _restore_from_tray(self):
        """被双击 exe 的新进程唤醒时调用，把隐藏的窗口重新显示出来"""
        self.deiconify()
        self.lift()
        self.focus_force()

    def _quit(self):
        if self.webdav:
            self.webdav.stop()
        if self.mobile:
            self.mobile.stop()
        self.notify_service.stop()
        self.destroy()
        sys.exit(0)


if __name__ == "__main__":
    # 先做单实例检测：如果已经有一份在后台运行，就只通知它显示窗口，
    # 本进程不创建界面、直接退出，避免重复开出多个窗口。
    _instance = SingleInstance()
    if not _instance.try_become_primary():
        sys.exit(0)

    app = App()
    _instance.on_show = lambda: app.after(0, app._restore_from_tray)
    app.mainloop()
