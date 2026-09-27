"""Envio de alertas pelo Telegram (grátis, chega no celular na hora)."""
from __future__ import annotations

import html
import os

import requests

from radar.engine import Alert


def format_alert(a: Alert) -> str:
    msg = f"<b>{html.escape(a.title)}</b>\n{html.escape(a.text)}"
    if a.link:
        msg += f'\n<a href="{html.escape(a.link, quote=True)}">Abrir</a>'
    return msg


def send_telegram(alerts: list[Alert], token: str | None = None, chat_id: str | None = None,
                  dashboard_url: str | None = None) -> int:
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    dashboard_url = dashboard_url or os.environ.get("DASHBOARD_URL")
    if not alerts:
        return 0
    if not token or not chat_id:
        print("(Telegram não configurado — alertas só no terminal)")
        for a in alerts:
            print(f"- {a.title}: {a.text} {a.link}")
        return 0
    sent = 0
    # Agrupa em mensagens de até ~3500 caracteres (limite do Telegram é 4096).
    chunks, cur = [], ""
    for a in alerts:
        piece = format_alert(a)
        if cur and len(cur) + len(piece) > 3500:
            chunks.append(cur)
            cur = ""
        cur += ("\n\n" if cur else "") + piece
    if dashboard_url:
        cur += f'\n\n<a href="{html.escape(dashboard_url, quote=True)}">📊 Ver painel</a>'
    chunks.append(cur)
    for text in chunks:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=30, json={
            "chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True,
        })
        r.raise_for_status()
        sent += 1
    return sent
