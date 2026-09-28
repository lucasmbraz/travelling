"""Junta as fontes de dados, calcula as melhores opções e decide o que vira alerta."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from radar import analysis as an
from radar import links
from radar.airports import city, label
from radar.config import Config, Group, Route, Window
from radar.models import Deal, Offer, Promo, Trip
from radar.providers import promos as promo_mod

AZUL = "AD"
ANYWHERE_CACHE_DAYS = 3  # destinos conferidos em rodadas anteriores continuam no painel


@dataclass
class GroupResult:
    """Preços de uma rota para um grupo de viajantes (valores = total do grupo)."""

    group: Group
    out_cash: dict[date, Offer]
    back_cash: dict[date, Offer]
    trips: dict[str, list[Trip]]  # nome da janela -> melhores idas/voltas


@dataclass
class PointsWindow:
    """Pontos Azul numa janela, por pessoa."""

    window: Window
    award: list[Trip]  # resgates reais (Seats.aero)
    azul: list[Trip]   # passagens da Azul em R$, base da estimativa


@dataclass
class RouteReport:
    route: Route
    groups: list[GroupResult]
    azul_out: dict[date, Offer]
    azul_back: dict[date, Offer]
    out_award: dict[date, Offer]
    back_award: dict[date, Offer]
    points: list[PointsWindow]

    @property
    def main(self) -> GroupResult:
        return self.groups[0]


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
    deals_checked: dict[str, date] = field(default_factory=dict)  # destino -> quando foi conferido
    award_deals: list[Offer] = field(default_factory=list)
    promos: list[Promo] = field(default_factory=list)
    bonuses: dict[str, Promo] = field(default_factory=dict)
    alerts: list[Alert] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    has_award_data: bool = False
    calibration: an.PointsCalibration | None = None
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


def _deal_to_json(d: Deal, checked: date) -> dict:
    return {"dest": d.destination, "depart": d.depart.isoformat(), "ret": d.ret.isoformat() if d.ret else None,
            "price": d.price, "pax": d.pax, "provider": d.provider, "link": d.link, "checked": checked.isoformat()}


def _deal_from_json(origin: str, j: dict) -> Deal:
    return Deal(origin, j["dest"], date.fromisoformat(j["depart"]),
                date.fromisoformat(j["ret"]) if j.get("ret") else None, float(j["price"]),
                link=j.get("link", ""), provider=j.get("provider", ""), pax=int(j.get("pax", 1)))


def build_report(cfg: Config, cash: list, award, promo_src, today: date, demo: bool = False,
                 state: dict | None = None) -> Report:
    """Monta o relatório combinando todas as fontes de preço em ``cash``.

    Para cada dia fica o menor preço entre as fontes; se uma fonte falhar, as
    outras continuam e o erro vai para os avisos. ``state`` guarda o rodízio de
    destinos entre uma rodada e outra.
    """
    rep = Report(cfg=cfg, today=today, demo=demo)
    start, end = cfg.horizon(today)

    def fetch(o: str, d: str, s: date, e: date, providers, adults: int = 1, children: int = 0,
              airline: str | None = None) -> list[Offer]:
        offers: list[Offer] = []
        for p in providers:
            got = _safe(rep.errors, f"{p.name} {o}→{d}",
                        lambda: p.one_way_range(o, d, s, e, adults=adults, children=children, airline=airline), [])
            rep.source_counts[p.name] = rep.source_counts.get(p.name, 0) + len(got)
            offers += got
        return [x for x in offers if x.day > today]

    # --- rotas fixas (Maceió, Recife...) -----------------------------------
    for route in cfg.routes:
        o, d = cfg.origin, route.destination
        groups = []
        for g in cfg.groups:
            outs = an.cheapest_by_day(fetch(o, d, start, end, cash, g.adults, g.children))
            backs = an.cheapest_by_day(fetch(d, o, start, end, cash, g.adults, g.children))
            trips = {w.name: an.best_round_trips(outs, backs, w.start, w.end, w.min_stay, w.max_stay,
                                                 extra_cost=route.extra_cost) for w in cfg.windows}
            groups.append(GroupResult(g, outs, backs, trips))
        azul_out = an.cheapest_by_day(fetch(o, d, start, end, cash, airline=AZUL))
        azul_back = an.cheapest_by_day(fetch(d, o, start, end, cash, airline=AZUL))
        a_out, a_back = [], []
        if award:
            a_out = _safe(rep.errors, f"pontos {o}→{d}", lambda: award.one_way(o, [d], start, end), [])
            a_back = _safe(rep.errors, f"pontos {d}→{o}", lambda: award.one_way(d, [o], start, end), [])
        out_award = an.cheapest_by_day([x for x in a_out if x.day > today], an.points_key)
        back_award = an.cheapest_by_day([x for x in a_back if x.day > today], an.points_key)
        points = [PointsWindow(
            window=w,
            award=an.best_round_trips(out_award, back_award, w.start, w.end, w.min_stay, w.max_stay, points=True),
            azul=an.best_round_trips(azul_out, azul_back, w.start, w.end, w.min_stay, w.max_stay),
        ) for w in cfg.windows]
        rr = RouteReport(route, groups, azul_out, azul_back, out_award, back_award, points)
        main = rr.main
        if not main.out_cash or not main.back_cash:
            rep.errors.append(
                f"{o}⇄{d}: nenhum preço em R$ encontrado para {main.group.name} "
                f"(ida: {len(main.out_cash)} dias, volta: {len(main.back_cash)} dias)")
        rep.has_award_data |= bool(out_award or back_award)
        rep.routes.append(rr)

    # --- calibração dos pontos Azul ------------------------------------------
    azul_prices = {}
    for rr in rep.routes:
        for day, off in list(rr.azul_out.items()) + list(rr.azul_back.items()):
            azul_prices[(off.origin, off.destination, day)] = off.price
    rep.calibration = an.calibrate_points(
        cfg.points_samples, lambda o, d, day: azul_prices.get((o, d, day)), cfg.point_value)

    # --- qualquer destino ----------------------------------------------------
    g = cfg.main_group
    n = g.size
    # 1) cache de buscas (Travelpayouts, preço de 1 adulto): descobre destinos.
    deals: list[Deal] = []
    for p in cash:
        if not hasattr(p, "anywhere_month"):
            continue
        for (y, m) in cfg.months_ahead(today, cfg.anywhere_months):
            got = _safe(rep.errors, f"{p.name} qualquer destino {m:02d}/{y}",
                        lambda: p.anywhere_month(cfg.origin, y, m), [])
            rep.source_counts[p.name] = rep.source_counts.get(p.name, 0) + len(got)
            deals += [replace(x, price=x.price * n, pax=n,
                              provider=x.provider if n == 1 else f"{x.provider} (×{n} estimado)") for x in got]
    deals = [x for x in deals if x.depart > today]
    for x in deals:
        rep.deals_checked[x.destination] = today

    # 2) calendário completo (Google Voos), em rodízio pelos candidatos.
    calendar_sources = [p for p in cash if getattr(p, "calendar", False)]
    mem = state.setdefault("anywhere", {}) if state is not None else {}
    cache: dict = mem.setdefault("deals", {})
    if calendar_sources:
        a_start, a_end = today + timedelta(days=1), today + timedelta(days=30 * cfg.anywhere_months)
        found = [x.destination for x in an.best_deals(deals, cfg.anywhere_exclude, top=50)]
        route_dests = {r.destination for r in cfg.routes}
        candidates: list[str] = []
        for code in cfg.anywhere_candidates + found:
            if code not in candidates and code != cfg.origin and code not in cfg.anywhere_exclude \
                    and code not in route_dests:
                candidates.append(code)
        batch = candidates
        if len(candidates) > cfg.anywhere_max_dest:
            offset = int(mem.get("offset", 0)) % len(candidates)
            batch = (candidates[offset:] + candidates[:offset])[:cfg.anywhere_max_dest]
            mem["offset"] = offset + cfg.anywhere_max_dest
        for dest in batch:
            outs = an.cheapest_by_day(fetch(cfg.origin, dest, a_start, a_end, calendar_sources, g.adults, g.children))
            backs = an.cheapest_by_day(fetch(dest, cfg.origin, a_start, a_end, calendar_sources, g.adults, g.children)) \
                if outs else {}
            trips = an.best_round_trips(outs, backs, a_start, a_end, cfg.anywhere_min_stay,
                                        cfg.anywhere_max_stay, top=1)
            if not trips:
                cache.pop(dest, None)
                continue
            t = trips[0]
            deal = Deal(cfg.origin, dest, t.out.day, t.back.day, t.total_price,
                        link=links.google_flights(cfg.origin, dest, t.out.day, t.back.day, g.adults, g.children),
                        provider=t.out.provider, pax=n)
            cache[dest] = _deal_to_json(deal, today)
            deals.append(deal)
            rep.deals_checked[dest] = today
        # destinos conferidos nas rodadas anteriores continuam valendo por alguns dias
        for dest, j in list(cache.items()):
            checked = date.fromisoformat(j["checked"])
            if (today - checked).days > ANYWHERE_CACHE_DAYS or int(j.get("pax", 1)) != n:
                del cache[dest]
                continue
            if dest in batch or dest in cfg.anywhere_exclude:
                continue
            deal = _deal_from_json(cfg.origin, j)
            if deal.depart > today:
                deals.append(deal)
                rep.deals_checked.setdefault(dest, checked)
    # Maceió, Recife etc. já têm seção própria no painel
    rep.deals = an.best_deals(deals, cfg.anywhere_exclude + [r.destination for r in cfg.routes], top=25)
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
    # chaves antigas (antes dos grupos de viajantes) não servem mais de comparação
    for k in [k for k in history if k.endswith(("|brl", "|qualquer"))]:
        del history[k]
    for k in [k for k in state.get("alerted", {}) if k.endswith(("|brl", "|qualquer"))]:
        del state["alerted"][k]
    alerts: list[Alert] = []
    g = cfg.main_group
    n = g.size

    for rr in rep.routes:
        r = rr.route
        where = f"{label(cfg.origin)} ⇄ {label(r.destination)}"
        for w in cfg.windows:
            trips = rr.main.trips.get(w.name) or []
            if trips:
                t = trips[0]
                pp = t.total_price / n
                key = f"{cfg.origin}-{r.destination}|{w.name}|{g.key}|pp"
                previous = _record(history, key, today, pp)
                dates = f"{_fmt_day(t.out.day)} → {_fmt_day(t.back.day)} ({t.nights} noites)"
                total = f"{g.name}: {_brl(t.total_price)} ({_brl(pp)}/pessoa)" if n > 1 else _brl(t.total_price)
                link = links.google_flights(cfg.origin, r.destination, t.out.day, t.back.day, g.adults, g.children)
                if _below_target(state, key, pp, r.target_price):
                    alerts.append(Alert(f"alvo|{key}", f"🎯 {where} abaixo do alvo",
                                        f"{w.name}: {total} — {dates}. Seu alvo: {_brl(r.target_price)}/pessoa.",
                                        link, PRIORITY_URGENT))
                elif previous and pp < min(previous) * (1 - cfg.drop_pct / 100):
                    alerts.append(Alert(f"queda|{key}", f"📉 Preço caiu: {where}",
                                        f"{w.name}: {total} (antes {_brl(min(previous))}/pessoa) — {dates}.", link))
            pw = next((p for p in rr.points if p.window.name == w.name), None)
            if pw and pw.award:
                t = pw.award[0]
                key = f"{cfg.origin}-{r.destination}|{w.name}|pts"
                previous = _record(history, key, today, t.total_points)
                dates = f"{_fmt_day(t.out.day)} → {_fmt_day(t.back.day)} ({t.nights} noites)"
                link = links.azul(cfg.origin, r.destination, t.out.day, t.back.day, True, g.adults, g.children)
                txt = f"{w.name}: {_pts(t.total_points)}/pessoa ({_pts(t.total_points * n)} para {g.name}) — {dates}."
                if _below_target(state, key, t.total_points, r.target_points):
                    alerts.append(Alert(f"alvo|{key}", f"🎯 {where} em pontos abaixo do alvo",
                                        txt + f" Seu alvo: {_pts(r.target_points)}/pessoa.", link, PRIORITY_URGENT))
                elif previous and t.total_points < min(previous) * (1 - cfg.drop_pct / 100):
                    alerts.append(Alert(f"queda|{key}", f"📉 Pontos caíram: {where}",
                                        txt + f" Antes {_pts(min(previous))}/pessoa.", link))

    for d in rep.deals:
        key = f"{cfg.origin}-{d.destination}|qualquer|{g.key}|pp"
        _record(history, key, today, d.per_person)
        if _below_target(state, key, d.per_person, cfg.anywhere_max_price):
            back = f" → {_fmt_day(d.ret)}" if d.ret else ""
            total = f"{_brl(d.price)} para {g.name} ({_brl(d.per_person)}/pessoa)" if d.pax > 1 else _brl(d.price)
            alerts.append(Alert(f"oport|{key}", f"✈️ Oportunidade: {label(d.destination)}",
                                f"{total} ida e volta, {_fmt_day(d.depart)}{back}.",
                                d.link or links.google_flights(cfg.origin, d.destination, d.depart, d.ret,
                                                               g.adults, g.children)))

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
