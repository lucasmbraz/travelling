"""Linha de comando.

    python -m radar painel            # atualiza dados, gera site/index.html e envia alertas
    python -m radar datas MCZ --de 2026-12-10 --ate 2027-01-15 --min 7 --max 20
    python -m radar pontos 32000      # de onde tirar os pontos para um resgate
    python -m radar painel --demo     # sem chaves, dados fictícios
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from radar import analysis as an
from radar.airports import label
from radar.config import Window, load_config
from radar.engine import build_report, compute_alerts, load_state, save_state
from radar.site import brl, dm, pts


def _providers(cfg, demo: bool, today: date):
    from radar.providers import demo as demo_mod
    from radar.providers.promos import PromoProvider

    if demo:
        return demo_mod.DemoCashProvider(), demo_mod.DemoAwardProvider(), demo_mod.DemoPromoProvider(today)
    tp_token = os.environ.get("TRAVELPAYOUTS_TOKEN")
    seats_key = os.environ.get("SEATS_AERO_KEY")
    if not tp_token:
        sys.exit("Defina TRAVELPAYOUTS_TOKEN (grátis em travelpayouts.com) ou use --demo.")
    from radar.providers.travelpayouts import TravelpayoutsProvider

    cash = TravelpayoutsProvider(tp_token)
    award = None
    if seats_key:
        from radar.providers.seatsaero import SeatsAeroProvider

        award = SeatsAeroProvider(seats_key)
    return cash, award, PromoProvider(cfg.feeds)


def cmd_painel(args) -> int:
    today = date.fromisoformat(args.hoje) if args.hoje else date.today()
    cfg = load_config(args.config, today)
    if args.demo and not any(cfg.balances.values()):
        cfg.balances = {"azul": 12000, "livelo": 30000, "cartao": 15000}  # saldos fictícios
    cash, award, promos = _providers(cfg, args.demo, today)
    rep = build_report(cfg, cash, award, promos, today, demo=args.demo)

    state_path = Path(args.estado)
    state = load_state(state_path)
    alerts = compute_alerts(rep, state)
    if not args.demo:
        save_state(state_path, state)

    from radar.site import render

    out = Path(args.saida)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render(rep), encoding="utf-8")
    print(f"Painel gerado em {out / 'index.html'} — {len(alerts)} alerta(s), {len(rep.errors)} aviso(s).")
    for e in rep.errors:
        print(f"  aviso: {e}")

    if args.sem_alertas or args.demo:
        for al in alerts:
            print(f"- {al.title}: {al.text}")
        return 0
    from radar.notify import send_telegram

    send_telegram(alerts)
    return 0


def cmd_datas(args) -> int:
    """Busca rápida no terminal: melhores idas/voltas para um destino e período."""
    today = date.today()
    cfg = load_config(args.config, today)
    cash, award, _ = _providers(cfg, args.demo, today)
    o, d = cfg.origin, args.destino.upper()
    start, end = date.fromisoformat(args.de), date.fromisoformat(args.ate)
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    outs = an.cheapest_by_day(x for (y, m) in months for x in cash.one_way_month(o, d, y, m))
    backs = an.cheapest_by_day(x for (y, m) in months for x in cash.one_way_month(d, o, y, m))
    w = Window("busca", start, end, args.min, args.max)
    trips = an.best_round_trips(outs, backs, w.start, w.end, w.min_stay, w.max_stay, top=args.top)
    print(f"{label(o)} ⇄ {label(d)} · ida a partir de {start:%d/%m/%Y}, volta até {end:%d/%m/%Y}, "
          f"{args.min}–{args.max} noites\n")
    if not trips:
        print("Nenhuma combinação encontrada com os dados disponíveis.")
    for t in trips:
        print(f"  {dm(t.out.day)} → {dm(t.back.day)}  {t.nights:>2} noites   {brl(t.total_price):>10}")
    if award:
        a_out = an.cheapest_by_day(award.one_way(o, [d], start, end), an.points_key)
        a_back = an.cheapest_by_day(award.one_way(d, [o], start, end), an.points_key)
        a_trips = an.best_round_trips(a_out, a_back, start, end, args.min, args.max, points=True, top=args.top)
        if a_trips:
            print("\nEm pontos Azul:")
            for t in a_trips:
                print(f"  {dm(t.out.day)} → {dm(t.back.day)}  {t.nights:>2} noites   "
                      f"{pts(t.total_points):>7} pts + {brl(t.out.price + t.back.price)}")
    return 0


def cmd_pontos(args) -> int:
    cfg = load_config(args.config)
    bonuses = {k: v for k, v in (b.split("=") for b in args.bonus)} if args.bonus else {}
    bonuses = {k: float(v) for k, v in bonuses.items()}
    plan = an.plan_points(cfg, args.necessarios, bonuses)
    print(f"Precisa de {pts(plan.needed)} pontos Azul.")
    if plan.from_azul:
        print(f"  • use {pts(plan.from_azul)} pontos que já estão na Azul")
    for s in plan.transfers:
        print(f"  • transfira {pts(s.source_points)} de {s.program.name} (bônus {s.bonus:.0f}%) → chegam {pts(s.azul_points)}")
    print("  ✅ dá para emitir!" if plan.feasible else f"  ❌ faltam {pts(plan.missing)} pontos")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="radar", description="Radar pessoal de passagens baratas")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--demo", action="store_true", help="usa dados fictícios (não precisa de chaves)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("painel", help="atualiza tudo, gera o painel e envia alertas")
    s.add_argument("--saida", default="site")
    s.add_argument("--estado", default="data/state.json")
    s.add_argument("--sem-alertas", action="store_true", help="não envia Telegram, só mostra no terminal")
    s.add_argument("--hoje", help=argparse.SUPPRESS)
    s.set_defaults(fn=cmd_painel)

    s = sub.add_parser("datas", help="melhores datas de ida e volta para um destino")
    s.add_argument("destino")
    s.add_argument("--de", required=True, help="primeiro dia possível de ida (AAAA-MM-DD)")
    s.add_argument("--ate", required=True, help="último dia possível de volta (AAAA-MM-DD)")
    s.add_argument("--min", type=int, default=5, help="mínimo de noites")
    s.add_argument("--max", type=int, default=15, help="máximo de noites")
    s.add_argument("--top", type=int, default=10)
    s.set_defaults(fn=cmd_datas)

    s = sub.add_parser("pontos", help="de onde tirar os pontos para um resgate")
    s.add_argument("necessarios", type=int)
    s.add_argument("--bonus", nargs="*", help="ex.: livelo=100 cartao=80")
    s.set_defaults(fn=cmd_pontos)

    args = p.parse_args(argv)
    return args.fn(args)
