"""Teste de viabilidade: dá para ler os preços em pontos do site da Azul?

Abre a busca da Azul em pontos num navegador (Chromium via Playwright), sem login,
e registra o que aconteceu: status das páginas, se houve bloqueio, quais respostas
JSON o próprio site carregou (é daí que sairiam os pontos) e um print da tela.
Não tenta driblar nenhuma proteção: se for bloqueado, só registra.

Uso: python tools/teste_azul.py BEL FOR 2026-11-10 saida/
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar.links import azul  # noqa: E402

BLOCK_HINTS = ("access denied", "captcha", "request unsuccessful", "you have been blocked",
               "unusual traffic", "acesso negado", "bot")


def main(origin: str, dest: str, day: str, out_dir: str) -> int:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    url = azul(origin, dest, date.fromisoformat(day), points=True)
    report: dict = {"url": url, "responses": [], "json": []}

    with sync_playwright() as p:
        exe = os.environ.get("CHROMIUM_PATH")  # só para testes locais
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        ctx = browser.new_context(locale="pt-BR", timezone_id="America/Belem",
                                  viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        def on_response(resp):
            try:
                ctype = resp.headers.get("content-type", "")
                item = {"url": resp.url[:300], "status": resp.status, "type": ctype[:60]}
                report["responses"].append(item)
                if "json" in ctype and "voeazul" in resp.url:
                    body = resp.text()
                    idx = len(report["json"])
                    (out / f"resposta_{idx:02d}.json").write_text(body, encoding="utf-8")
                    try:
                        data = json.loads(body)
                        keys = list(data)[:15] if isinstance(data, dict) else f"lista[{len(data)}]"
                    except Exception:
                        keys = "?"
                    report["json"].append({**item, "file": f"resposta_{idx:02d}.json", "bytes": len(body),
                                           "keys": keys,
                                           "menciona_pontos": bool(re.search(r"point|pontos|loyalty|miles",
                                                                             body, re.I))})
            except Exception as e:  # algumas respostas não têm corpo (redirect etc.)
                report["responses"].append({"url": resp.url[:300], "erro": str(e)[:100]})

        page.on("response", on_response)
        try:
            first = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            report["status_inicial"] = first.status if first else None
            page.wait_for_timeout(25000)  # dá tempo para o site buscar os voos
        except Exception as e:
            report["erro_navegacao"] = f"{type(e).__name__}: {e}"[:300]
        report["url_final"] = page.url
        report["titulo"] = page.title()
        text = page.inner_text("body")[:4000] if page.query_selector("body") else ""
        (out / "texto_da_pagina.txt").write_text(text, encoding="utf-8")
        report["parece_bloqueado"] = any(h in text.lower() for h in BLOCK_HINTS) or \
            (report.get("status_inicial") or 200) in (403, 429)
        report["pontos_no_texto"] = re.findall(r"[\d.]{4,9}\s*pontos", text, re.I)[:20]
        page.screenshot(path=str(out / "tela.png"), full_page=False)
        browser.close()

    (out / "relatorio.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"URL: {url}")
    print(f"Status inicial: {report.get('status_inicial')} · final: {report['url_final'][:120]}")
    print(f"Título: {report['titulo']!r}")
    print(f"Parece bloqueado: {report['parece_bloqueado']}")
    print(f"Respostas: {len(report['responses'])} · JSON da Azul: {len(report['json'])}")
    for j in report["json"]:
        print(f"  {j['status']} {j['bytes']:>7}B pontos={j['menciona_pontos']} {j['url'][:110]}")
    print(f"'pontos' no texto da página: {report['pontos_no_texto']}")
    if report.get("erro_navegacao"):
        print("Erro:", report["erro_navegacao"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:5]))
