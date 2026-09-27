"""Junta as fontes de dados, calcula as melhores opções e decide o que vira alerta."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from radar import analysis as an
from radar import links
from radar.airports import city, label
from radar.config import Config, Route, Window
from radar.models import Deal, Offer, Promo, Trip
from radar.providers import promos as promo_mod


@dataclass
class WindowResult:
    window: Window
    cash: list[Trip]
    award: list[Trip]


@dataclass
class RouteReport:
    route: Route
    out_cash: dict[date, Offer]
    back_cash: dict[date, Offer]
    out_award: dict[date, Offer]
    back_award: dict[date, Offer]
    windows: list[WindowResult]

    def best(self, points: bool) -> Trip | None:
        trips = [t for w in self.windows for t in (w.award if points else w.cash)]
        if not trips:
            return None
        return min(trips, key=lambda t: (t.total_points, t.total_price) if points else t.total_price)


# Prioridades de notificação (mesma escala do ntfy: 1 = mínima, 5 = urgente).
PRIORITY_LOW, PRIORITY_NORMAL, PRIORITY_URGENT = 2, 3, 5


@dataclass
class Alert:
    key: str
    title: str
    text: str
    link: str = ""
    priority: int = PRIORITY_NORMAL


@dataclass
class Report:
    cfg: Config
    today: date
    demo: bool
    routes: list[RouteReport] = field(default_factory=list)
    deals: list[Deal] = field(default_factory=list)
    award_deals: list[Offer] = field(default_factory=list)
    promos: list[Promo] = field(default_factory=list)
    bonuses: dict[str, Promo] = field(default_factory=dict)
    alerts: list[Alert] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    has_award_data: bool = False
    source_counts: dict[str, int] = field(default_factory=dict)  # preços recebidos por fonte
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="minutes"))

    @property
    def bonus_pcts(self) -> dict[str, float]:
        return {k: float(p.bonus_pct or 0) for k, p in self.bonuses.items()}


def _safe(errors: list[str], what: str, fn, default):
    try:
        return fn()
    except Exception as e:  # uma fonte com erro não pode derrubar o radar inteiro
        errors.append(f"{what}: {e}")
        return default


def build_report(cfg: Config, cash: list, award, promo_src, today: date, demo: bool = False) -> Report:
    """Monta o relatório combinando todas as fontes de preço em ``cash``.

    Para cada dia fica o menor preço entre as fontes; se uma fonte falhar, as
    outras continuam e o erro vai para os avisos.
    """
    rep = Report(cfg=cfg, today=today, demo=demo)
    start, end = cfg.horizon(today)

    def fetch(o: str, d: str, s: date, e: date, providers) -> list[Offer]:
        offers: list[Offer] = []
        for p in providers:
            got = _safe(rep.errors, f"{p.name} {o}→{d}", lambda: p.one_way_range(o, d, s, e), [])
            rep.source_counts[p.name] = rep.source_counts.get(p.name, 0) + len(got)
            offers += got
        return [x for x in offers if x.day > today]

    # --- rotas fixas (Maceió, Recife...) -----------------------------------
    for route in cfg.routes:
        o, d = cfg.origin, route.destination
        outs, backs = fetch(o, d, start, end, cash), fetch(d, o, start, end, cash)
        a_out, a_back = [], []
        if award:
            a_out = _safe(rep.errors, f"pontos {o}→{d}", lambda: award.one_way(o, [d], start, end), [])
            a_back = _safe(rep.errors, f"pontos {d}→{o}", lambda: award.one_way(d, [o], start, end), [])
        future = lambda xs: [x for x in xs if x.day > today]  # noqa: E731
        a_out, a_back = future(a_out), future(a_back)
        rr = RouteReport(
            route=route,
            out_cash=an.cheapest_by_day(outs), back_cash=an.cheapest_by_day(backs),
            out_award=an.cheapest_by_day(a_out, an.points_key), back_award=an.cheapest_by_day(a_back, an.points_key),
            windows=[],
        )
        for w in cfg.windows:
            rr.windows.append(WindowResult(
                window=w,
                cash=an.best_round_trips(rr.out_cash, rr.back_cash, w.start, w.end, w.min_stay, w.max_stay,
                                         extra_cost=route.extra_cost),
                award=an.best_round_trips(rr.out_award, rr.back_award, w.start, w.end, w.min_stay, w.max_stay,
                                          points=True, extra_cost=route.extra_cost),
            ))
        if not rr.out_cash or not rr.back_cash:
            rep.errors.append(
                f"{o}⇄{d}: nenhum preço em R$ encontrado "
                f"(ida: {len(rr.out_cash)} dias, volta: {len(rr.back_cash)} dias)")
        rep.has_award_data |= bool(rr.out_award or rr.back_award)
        rep.routes.append(rr)

    # --- qualquer destino ----------------------------------------------------
    # 1) cache de buscas (Travelpayouts): descobre destinos que você nem pensou.
    deals: list[Deal] = []
    for p in cash:
        if not hasattr(p, "anywhere_month"):
            continue
        for (y, m) in cfg.months_ahead(today, cfg.anywhere_months):
            got = _safe(rep.errors, f"{p.name} qualquer destino {m:02d}/{y}",
                        lambda: p.anywhere_month(cfg.origin, y, m), [])
            rep.source_counts[p.name] = rep.source_counts.get(p.name, 0) + len(got)
            deals += got
    deals = [d for d in deals if d.depart > today]

    # 2) calendário completo (Google Voos) para os candidatos + o que o cache achou.
    calendar_sources = [p for p in cash if getattr(p, "calendar", False)]
    if calendar_sources:
        a_start, a_end = today + timedelta(days=1), today + timedelta(days=30 * cfg.anywhere_months)
        found = [x.destination for x in an.best_deals(deals, cfg.anywhere_exclude, top=50)]
        route_dests = {r.destination for r in cfg.routes}
        candidates = []
        for code in cfg.anywhere_candidates + found:
            if code not in candidates and code != cfg.origin and code not in cfg.anywhere_exclude \
                    and code not in route_dests:
                candidates.append(code)
        for dest in candidates[:cfg.anywhere_max_dest]:
            outs = an.cheapest_by_day(fetch(cfg.origin, dest, a_start, a_end, calendar_sources))
            if not outs:
                continue
            backs = an.cheapest_by_day(fetch(dest, cfg.origin, a_start, a_end, calendar_sources))
            trips = an.best_round_trips(outs, backs, a_start, a_end, cfg.anywhere_min_stay,
                                        cfg.anywhere_max_stay, top=1)
            if trips:
                t = trips[0]
                deals.append(Deal(cfg.origin, dest, t.out.day, t.back.day, t.total_price,
                                  link=links.google_flights(cfg.origin, dest, t.out.day, t.back.day),
                                  provider=t.out.provider))
    rep.deals = an.best_deals(deals, cfg.anywhere_exclude)
    if award:
        a_end = today + timedelta(days=30 * cfg.anywhere_months)
        rep.award_deals = an.best_awards_anywhere(
            _safe(rep.errors, "pontos para qualquer destino",
                  lambda: award.anywhere(cfg.origin, today + timedelta(days=1), a_end), []),
            cfg.anywhere_exclude)

    # --- promoções ----------------------------------------------------------
    if promo_src:
        items, errs = _safe(rep.errors, "promoções", promo_src.fetch, ([], []))
        rep.errors += [f"feed {e}" for e in errs]
        interests = {"azul"} | {k for p in cfg.programs.values() for k in p.keywords}
        places = [cfg.origin, city(cfg.origin)] + [x for r in cfg.routes for x in (r.destination, city(r.destination))]
        rep.promos = promo_mod.relevant(items, interests, places, today, cfg.promo_recent_days)
        for key, prog in cfg.programs.items():
            p = promo_mod.active_bonus(rep.promos, prog.keywords)
            if p:
                rep.bonuses[key] = p
    return rep


# ---------------------------------------------------------------- alertas + histórico

def _brl(v: float) -> str:
    return f"R$ {v:,.0f}".replace(",", ".")


def _pts(v: int) -> str:
    return f"{v:,}".replace(",", ".") + " pts"


def _fmt_day(d: date) -> str:
    return d.strftime("%d/%m")


def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def _record(history: dict, key: str, today: date, value: float, keep_days: int = 180) -> list[float]:
    """Guarda o valor de hoje e devolve os valores anteriores (últimos 30 dias)."""
    series = [e for e in history.get(key, []) if (today - date.fromisoformat(e["t"])).days <= keep_days]
    previous = [e["v"] for e in series if e["t"] != today.isoformat()
                and (today - date.fromisoformat(e["t"])).days <= 30]
    series = [e for e in series if e["t"] != today.isoformat()]
    prior_today = [e["v"] for e in history.get(key, []) if e["t"] == today.isoformat()]
    series.append({"t": today.isoformat(), "v": min([value] + prior_today)})
    history[key] = series
    return previous


def _below_target(state: dict, key: str, value: float, target: float | None) -> bool:
    """True se está abaixo do alvo e ainda não avisamos esse preço (ou caiu mais 5%)."""
    alerted = state.setdefault("alerted", {})
    if target is None or value > target:
        alerted.pop(key, None)
        return False
    last = alerted.get(key)
    if last is not None and value > last * 0.95:
        return False
    alerted[key] = value
    return True


def compute_alerts(rep: Report, state: dict) -> list[Alert]:
    cfg, today = rep.cfg, rep.today
    history = state.setdefault("history", {})
    alerts: list[Alert] = []

    for rr in rep.routes:
        r = rr.route
        for wr in rr.windows:
            for points, trips in ((False, wr.cash), (True, wr.award)):
                if not trips:
                    continue
                t = trips[0]
                value = t.total_points if points else t.total_price
                kind = "pts" if points else "brl"
                key = f"{cfg.origin}-{r.destination}|{wr.window.name}|{kind}"
                previous = _record(history, key, today, value)
                fmt = _pts if points else _brl
                where = f"{label(cfg.origin)} ⇄ {label(r.destination)}"
                dates = f"{_fmt_day(t.out.day)} → {_fmt_day(t.back.day)} ({t.nights} noites)"
                link = links.azul(cfg.origin, r.destination, t.out.day, t.back.day, points) if points \
                    else links.google_flights(cfg.origin, r.destination, t.out.day, t.back.day)
                target = r.target_points if points else r.target_price
                if _below_target(state, key, value, target):
                    alerts.append(Alert(f"alvo|{key}", f"🎯 {where} abaixo do alvo",
                                        f"{wr.window.name}: {fmt(value)} — {dates}. Seu alvo: {fmt(target)}.", link,
                                        PRIORITY_URGENT))
                elif previous and value < min(previous) * (1 - cfg.drop_pct / 100):
                    alerts.append(Alert(f"queda|{key}", f"📉 Preço caiu: {where}",
                                        f"{wr.window.name}: {fmt(value)} (antes {fmt(min(previous))}) — {dates}.", link))

    for d in rep.deals:
        key = f"{cfg.origin}-{d.destination}|qualquer"
        _record(history, key, today, d.price)
        if _below_target(state, key, d.price, cfg.anywhere_max_price):
            back = f" → {_fmt_day(d.ret)}" if d.ret else ""
            alerts.append(Alert(f"oport|{key}", f"✈️ Oportunidade: {label(d.destination)}",
                                f"{_brl(d.price)} ida e volta, {_fmt_day(d.depart)}{back}.",
                                d.link or links.google_flights(cfg.origin, d.destination, d.depart, d.ret)))

    seen = state.setdefault("seen_promos", [])
    for p in rep.promos:
        if p.link in seen:
            continue
        seen.append(p.link)
        emoji = "💳" if p.kind == "transferencia" else "🏷️"
        urgent = p.kind == "transferencia" and "azul" in p.programs
        alerts.append(Alert(f"promo|{p.link}", f"{emoji} {p.title}", f"Fonte: {p.source}", p.link,
                            PRIORITY_URGENT if urgent else PRIORITY_LOW))
    state["seen_promos"] = seen[-500:]
    rep.alerts = alerts
    return alerts
