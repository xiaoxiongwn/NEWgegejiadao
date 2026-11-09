# -*- coding: utf-8 -*-
import qrcode


def make_qr_image(data, box_size=6, border=2):
    qr = qrcode.QRCode(box_size=box_size, border=border)
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color='black', back_color='white').convert('RGB')
