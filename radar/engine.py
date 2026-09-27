"""Junta as fontes de dados, calcula as melhores opções e decide o que vira alerta."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from radar import analysis as an
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


@dataclass
class Alert:
    key: str
    title: str
    text: str
    link: str = ""


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
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="minutes"))

    @property
    def bonus_pcts(self) -> dict[str, float]:
        return {k: float(p.bonus_pct or 0) for k, p in self.bonuses.items()}


def _months_between(start: date, end: date) -> list[tuple[int, int]]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _safe(errors: list[str], what: str, fn, default):
    try:
        return fn()
    except Exception as e:  # uma fonte com erro não pode derrubar o radar inteiro
        errors.append(f"{what}: {e}")
        return default


def build_report(cfg: Config, cash, award, promo_src, today: date, demo: bool = False) -> Report:
    rep = Report(cfg=cfg, today=today, demo=demo)
    start, end = cfg.horizon(today)
    months = _months_between(start, end)

    # --- rotas fixas (Maceió, Recife...) -----------------------------------
    for route in cfg.routes:
        o, d = cfg.origin, route.destination
        outs, backs = [], []
        for (y, m) in months:
            outs += _safe(rep.errors, f"preços {o}→{d} {m:02d}/{y}", lambda: cash.one_way_month(o, d, y, m), [])
            backs += _safe(rep.errors, f"preços {d}→{o} {m:02d}/{y}", lambda: cash.one_way_month(d, o, y, m), [])
        a_out, a_back = [], []
        if award:
            a_out = _safe(rep.errors, f"pontos {o}→{d}", lambda: award.one_way(o, [d], start, end), [])
            a_back = _safe(rep.errors, f"pontos {d}→{o}", lambda: award.one_way(d, [o], start, end), [])
        future = lambda xs: [x for x in xs if x.day > today]  # noqa: E731
        outs, backs, a_out, a_back = future(outs), future(backs), future(a_out), future(a_back)
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
        rep.has_award_data |= bool(rr.out_award or rr.back_award)
        rep.routes.append(rr)

    # --- qualquer destino ----------------------------------------------------
    deals = []
    for (y, m) in cfg.months_ahead(today, cfg.anywhere_months):
        deals += _safe(rep.errors, f"qualquer destino {m:02d}/{y}", lambda: cash.anywhere_month(cfg.origin, y, m), [])
    deals = [d for d in deals if d.depart > today]
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
    from radar import links

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
                                        f"{wr.window.name}: {fmt(value)} — {dates}. Seu alvo: {fmt(target)}.", link))
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
        alerts.append(Alert(f"promo|{p.link}", f"{emoji} {p.title}", f"Fonte: {p.source}", p.link))
    state["seen_promos"] = seen[-500:]
    rep.alerts = alerts
    return alerts
