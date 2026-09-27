"""Alertas como notificação push no celular via ntfy (https://ntfy.sh).

Grátis e sem cadastro: instale o app ntfy, assine um tópico com nome secreto e
coloque o mesmo nome em NTFY_TOPIC. Quem souber o nome do tópico consegue ler os
avisos, então use um nome longo e aleatório.
"""
from __future__ import annotations

import os

import requests

from radar.engine import Alert

DEFAULT_SERVER = "https://ntfy.sh"
MAX_INDIVIDUAL = 5  # acima disso, o resto vai resumido numa notificação só


def build_messages(alerts: list[Alert], topic: str, dashboard_url: str | None = None) -> list[dict]:
    """Monta os payloads JSON do ntfy, mais importantes primeiro."""
    ordered = sorted(alerts, key=lambda a: -a.priority)
    painel = [{"action": "view", "label": "Ver painel", "url": dashboard_url}] if dashboard_url else []
    msgs = []
    for a in ordered[:MAX_INDIVIDUAL]:
        msg = {"topic": topic, "title": a.title, "message": a.text, "priority": a.priority}
        if a.link:
            msg["click"] = a.link
        if painel:
            msg["actions"] = painel
        msgs.append(msg)
    rest = ordered[MAX_INDIVIDUAL:]
    if rest:
        msg = {
            "topic": topic,
            "title": f"E mais {len(rest)} alerta(s) do radar",
            "message": "\n".join(f"• {a.title}" for a in rest[:15]),
            "priority": max(a.priority for a in rest),
        }
        if dashboard_url:
            msg["click"] = dashboard_url
        msgs.append(msg)
    return msgs


def send_push(alerts: list[Alert], topic: str | None = None, server: str | None = None,
              dashboard_url: str | None = None) -> int:
    topic = topic or os.environ.get("NTFY_TOPIC")
    server = (server or os.environ.get("NTFY_SERVER") or DEFAULT_SERVER).rstrip("/")
    dashboard_url = dashboard_url or os.environ.get("DASHBOARD_URL") or None
    if not alerts:
        return 0
    if not topic:
        print("(NTFY_TOPIC não configurado — alertas só no terminal)")
        for a in alerts:
            print(f"- {a.title}: {a.text} {a.link}")
        return 0
    msgs = build_messages(alerts, topic, dashboard_url)
    for msg in msgs:
        # Publicar em JSON na raiz do servidor aceita acentos e emojis no título.
        r = requests.post(server, json=msg, timeout=30)
        r.raise_for_status()
    return len(msgs)
