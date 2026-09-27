"""Gera o painel em HTML estático (um arquivo só, sem JavaScript obrigatório)."""
from __future__ import annotations

import calendar
from datetime import date
from html import escape

from radar import analysis as an
from radar import links
from radar.airports import city, label
from radar.engine import Report, RouteReport, WindowResult
from radar.models import Offer, Trip

MONTHS = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]
WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
WD_SHORT = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def brl(v: float) -> str:
    return f"R$ {v:,.0f}".replace(",", ".")


def pts(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def kpts(v: int) -> str:
    return f"{v / 1000:.1f}k".replace(".0k", "k").replace(".", ",")


def dm(d: date) -> str:
    return f"{WD_SHORT[d.weekday()]} {d.day:02d}/{d.month:02d}"


def a(href: str, text: str) -> str:
    return f'<a href="{escape(href, quote=True)}" target="_blank" rel="noopener">{escape(text)}</a>'


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1a1d23;--muted:#5f6673;--line:#e3e6eb;--accent:#0b63ce;
--l0:#1a9850;--l1:#91cf60;--l2:#e8d44d;--l3:#fc8d59;--l4:#d73027;--none:#eceef1;--warn:#fff4d6;--warn-ink:#6b4e00;
--good:#e6f4ea;--good-ink:#135c2e;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#111418;--card:#1a1e24;--ink:#e8eaed;
--muted:#9aa3ad;--line:#2b3139;--accent:#6ea8fe;--none:#252a31;--warn:#3a2f10;--warn-ink:#f3d98b;--good:#12301d;
--good-ink:#9fe0b4;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#111418;--card:#1a1e24;--ink:#e8eaed;--muted:#9aa3ad;--line:#2b3139;--accent:#6ea8fe;
--none:#252a31;--warn:#3a2f10;--warn-ink:#f3d98b;--good:#12301d;--good-ink:#9fe0b4;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1080px;margin:0 auto;padding:16px}
h1{font-size:1.6rem;margin:.2em 0}h2{font-size:1.25rem;margin:0 0 .4em}h3{font-size:1.02rem;margin:1.1em 0 .4em}
.muted{color:var(--muted)}.small{font-size:.86rem}a{color:var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0}
.banner{background:var(--warn);color:var(--warn-ink);border-radius:10px;padding:10px 14px;margin:10px 0}
.good{background:var(--good);color:var(--good-ink);border-radius:10px;padding:10px 14px;margin:10px 0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.kpi{border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.kpi b{display:block;font-size:1.3rem}.kpi span{color:var(--muted);font-size:.85rem}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--muted);font-weight:600;font-size:.8rem;text-transform:uppercase;letter-spacing:.02em}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.best td{font-weight:600}
.months{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.cal{font-variant-numeric:tabular-nums}.cal h4{margin:0 0 4px;font-size:.9rem;text-transform:capitalize}
.grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}
.grid .wd{font-size:.68rem;color:var(--muted);text-align:center}
.day{border-radius:5px;min-height:38px;padding:2px 3px;font-size:.66rem;line-height:1.15;background:var(--none);
color:var(--muted)}
.day i{font-style:normal;display:block;opacity:.8}.day b{display:block;font-size:.72rem;font-weight:600}
.lv0{background:var(--l0);color:#fff}.lv1{background:var(--l1);color:#10240a}.lv2{background:var(--l2);color:#2b2500}
.lv3{background:var(--l3);color:#2a1000}.lv4{background:var(--l4);color:#fff}.empty{background:transparent}
.legend{display:flex;gap:6px;align-items:center;font-size:.8rem;color:var(--muted);flex-wrap:wrap;margin:6px 0}
.legend span{display:inline-block;width:18px;height:12px;border-radius:3px}
details>summary{cursor:pointer;font-weight:600;margin:.6em 0}
.tag{display:inline-block;font-size:.72rem;padding:1px 7px;border-radius:99px;border:1px solid var(--line);color:var(--muted)}
ul.promos{padding-left:1.1em}ul.promos li{margin:.35em 0}
nav{display:flex;gap:12px;flex-wrap:wrap;font-size:.9rem;margin:6px 0 0}
@media (max-width:560px){main{padding:12px}.day{min-height:34px;font-size:.6rem}.day b{font-size:.64rem}}
"""


def render(rep: Report) -> str:
    cfg = rep.cfg
    parts = [
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Radar de Passagens</title>",
        f"<style>{CSS}</style></head><body><main>",
        f"<h1>✈️ Radar de Passagens</h1><div class='muted small'>Saindo de {escape(label(cfg.origin))} · "
        f"atualizado em {escape(rep.generated_at.replace('T', ' ').replace('+00:00', ' UTC'))}</div>",
        "<nav>" + "".join(f"<a href='#rota-{r.route.destination}'>{escape(r.route.name)}</a>" for r in rep.routes)
        + "<a href='#oportunidades'>Oportunidades</a><a href='#promocoes'>Promoções</a></nav>",
    ]
    if rep.demo:
        parts.append("<div class='banner'><b>Modo demonstração:</b> todos os preços e promoções desta página são "
                     "FICTÍCIOS. Configure os tokens (veja o README) para ver dados reais.</div>")
    parts.append(_wallet(rep))
    for rr in rep.routes:
        parts.append(_route(rep, rr))
    parts.append(_anywhere(rep))
    parts.append(_promos(rep))
    if rep.errors:
        items = "".join(f"<li>{escape(e)}</li>" for e in rep.errors[:40])
        parts.append(f"<div class='card'><details><summary>Avisos da última atualização ({len(rep.errors)})</summary>"
                     f"<ul class='small muted'>{items}</ul></details></div>")
    parts.append(_footer(rep))
    parts.append("</main></body></html>")
    return "\n".join(parts)


# ------------------------------------------------------------------ carteira

def _wallet(rep: Report) -> str:
    cfg = rep.cfg
    now = an.azul_power(cfg)
    with_bonus = an.azul_power(cfg, rep.bonus_pcts)
    kpis = [f"<div class='kpi'><b>{pts(cfg.balances.get('azul', 0))}</b><span>pontos Azul Fidelidade</span></div>"]
    for key, prog in cfg.programs.items():
        kpis.append(f"<div class='kpi'><b>{pts(cfg.balances.get(key, 0))}</b><span>{escape(prog.name)}</span></div>")
    kpis.append(f"<div class='kpi'><b>{pts(now)}</b><span>pontos Azul se transferir tudo hoje</span></div>")
    out = ["<section class='card' id='carteira'><h2>Seus pontos</h2>", f"<div class='kpis'>{''.join(kpis)}</div>"]
    if rep.bonuses:
        lines = []
        for key, promo in rep.bonuses.items():
            prog = cfg.programs[key]
            bal = cfg.balances.get(key, 0)
            gain = int(bal * prog.ratio * (promo.bonus_pct or 0) / 100)
            lines.append(f"<li><b>{escape(prog.name)} → Azul com até {promo.bonus_pct}% de bônus</b> — "
                         f"{a(promo.link, promo.title)}"
                         + (f" <span class='muted'>(com seu saldo: +{pts(gain)} pontos)</span>" if bal else "")
                         + "</li>")
        out.append("<div class='good'><b>Promoção de transferência no ar!</b><ul class='promos'>" + "".join(lines)
                   + f"</ul>Com esses bônus seu poder de compra vai para <b>{pts(with_bonus)} pontos Azul</b>. "
                   "Confira as regras (o bônus costuma variar com o Clube Azul) antes de transferir.</div>")
    else:
        out.append("<p class='muted small'>Nenhuma promoção de transferência para a Azul detectada nos últimos "
                   f"{cfg.promo_recent_days} dias. Quando aparecer, você recebe um alerta.</p>")
    if not any(cfg.balances.values()):
        out.append("<p class='muted small'>Dica: coloque seus saldos em <code>config.yaml</code> para o radar dizer "
                   "quanto transferir de cada programa.</p>")
    out.append("</section>")
    return "".join(out)


# ------------------------------------------------------------------ rotas

def _route(rep: Report, rr: RouteReport) -> str:
    cfg, r = rep.cfg, rr.route
    o, d = cfg.origin, r.destination
    head = f"{escape(label(o))} ⇄ {escape(label(d))}"
    out = [f"<section class='card' id='rota-{d}'><h2>{escape(r.name)}</h2><div class='muted small'>{head}"]
    if r.extra_cost:
        out.append(f" · totais incluem {brl(r.extra_cost)} de custo extra"
                   + (f" ({escape(r.note)})" if r.note else ""))
    out.append("</div>")

    if not rr.out_cash and not rr.out_award:
        out.append("<p class='muted'>Sem dados de preço para essa rota ainda. As fontes funcionam a partir de buscas "
                   "recentes; tente de novo mais tarde.</p></section>")
        return "".join(out)

    for wr in rr.windows:
        out.append(_window(rep, rr, wr))

    out.append(_calendars(f"Calendário de preços — ida ({city(o)} → {city(d)})", rr.out_cash, False, open_=True))
    out.append(_calendars(f"Calendário de preços — volta ({city(d)} → {city(o)})", rr.back_cash, False))
    if rr.out_award or rr.back_award:
        out.append(_calendars(f"Calendário em pontos Azul — ida ({city(o)} → {city(d)})", rr.out_award, True))
        out.append(_calendars(f"Calendário em pontos Azul — volta ({city(d)} → {city(o)})", rr.back_award, True))
    out.append("</section>")
    return "".join(out)


def _window(rep: Report, rr: RouteReport, wr: WindowResult) -> str:
    cfg, r, w = rep.cfg, rr.route, wr.window
    o, d = cfg.origin, r.destination
    out = [f"<h3>{escape(w.name)} <span class='tag'>{w.start:%d/%m/%y} a {w.end:%d/%m/%y} · "
           f"{w.min_stay}–{w.max_stay} noites</span></h3>"]
    if wr.cash:
        best = wr.cash[0]
        out.append(f"<div class='good'>Mais barato em dinheiro: <b>{brl(best.total_price)}</b> ida e volta — "
                   f"{dm(best.out.day)} → {dm(best.back.day)} ({best.nights} noites).</div>")
        rows = []
        for i, t in enumerate(wr.cash):
            rows.append(
                f"<tr class='{'best' if i == 0 else ''}'><td>{dm(t.out.day)}</td><td>{dm(t.back.day)}</td>"
                f"<td class='num'>{t.nights}</td><td class='num'>{brl(t.out.price)}</td>"
                f"<td class='num'>{brl(t.back.price)}</td><td class='num'>{brl(t.total_price)}</td>"
                f"<td>{escape(_airlines(t))}</td>"
                f"<td>{a(links.google_flights(o, d, t.out.day, t.back.day), 'Google Voos')} · "
                f"{a(links.azul(o, d, t.out.day, t.back.day), 'Azul')}</td></tr>")
        out.append("<div class='scroll'><table><thead><tr><th>Ida</th><th>Volta</th><th>Noites</th><th>Ida R$</th>"
                   "<th>Volta R$</th><th>Total</th><th>Cia</th><th>Conferir</th></tr></thead><tbody>"
                   + "".join(rows) + "</tbody></table></div>")
    else:
        out.append("<p class='muted small'>Sem combinação em dinheiro com dados suficientes nessa janela.</p>")

    if wr.award:
        out.append(_award_table(rep, rr, wr.award))
    elif not rep.has_award_data:
        est = wr.cash[0] if wr.cash else None
        if est:
            p = an.estimate_points(est.total_price - r.extra_cost, cfg.point_value)
            out.append(f"<p class='small muted'>Em pontos Azul, essa viagem deve ficar por volta de <b>{pts(p)}</b> "
                       f"(estimativa a R$ {cfg.point_value:.0f} o milheiro — ative o Seats.aero para ver valores reais)."
                       "</p>")
    return "".join(out)


def _award_table(rep: Report, rr: RouteReport, trips: list[Trip]) -> str:
    cfg, r = rep.cfg, rr.route
    o, d = cfg.origin, r.destination
    best = trips[0]
    plan = an.plan_points(cfg, best.total_points, rep.bonus_pcts)
    cash_same = _cash_for(rr, best)
    lines = [f"Mais barato em pontos: <b>{pts(best.total_points)} pontos Azul</b> + {brl(best.out.price + best.back.price)}"
             f" de taxas — {dm(best.out.day)} → {dm(best.back.day)} ({best.nights} noites)."]
    if cash_same:
        v = an.value_per_thousand(cash_same, best.total_points, best.out.price + best.back.price)
        if v:
            verdict = "✅ vale usar pontos" if v >= cfg.point_value else "💸 melhor pagar em dinheiro"
            lines.append(f"Nas mesmas datas, em dinheiro sai {brl(cash_same)} → cada 1.000 pontos valem "
                         f"<b>R$ {v:.2f}</b> ({verdict}; sua régua é R$ {cfg.point_value:.0f}).")
    lines.append(_plan_text(cfg, plan))
    rows = []
    for i, t in enumerate(trips):
        rows.append(
            f"<tr class='{'best' if i == 0 else ''}'><td>{dm(t.out.day)}</td><td>{dm(t.back.day)}</td>"
            f"<td class='num'>{t.nights}</td><td class='num'>{pts(t.out.points)}</td><td class='num'>{pts(t.back.points)}</td>"
            f"<td class='num'>{pts(t.total_points)}</td><td class='num'>{brl(t.out.price + t.back.price)}</td>"
            f"<td>{a(links.azul(o, d, t.out.day, t.back.day, points=True), 'Azul (pontos)')}</td></tr>")
    return ("<div class='good'>" + "<br>".join(lines) + "</div>"
            "<div class='scroll'><table><thead><tr><th>Ida</th><th>Volta</th><th>Noites</th><th>Ida pts</th>"
            "<th>Volta pts</th><th>Total pts</th><th>Taxas</th><th>Conferir</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")


def _cash_for(rr: RouteReport, t: Trip) -> float | None:
    o, b = rr.out_cash.get(t.out.day), rr.back_cash.get(t.back.day)
    return o.price + b.price if o and b else None


def _plan_text(cfg, plan: an.PointsPlan) -> str:
    if not any(cfg.balances.values()):
        return "<span class='muted'>Informe seus saldos no config.yaml para ver de onde tirar os pontos.</span>"
    bits = []
    if plan.from_azul:
        bits.append(f"use {pts(plan.from_azul)} pontos Azul")
    for s in plan.transfers:
        extra = f" com {s.bonus:.0f}% de bônus" if s.bonus else ""
        bits.append(f"transfira {pts(s.source_points)} {escape(s.program.name)}{extra} (chegam {pts(s.azul_points)})")
    txt = "Plano: " + "; ".join(bits) + "." if bits else ""
    if plan.missing:
        txt += f" <b>Faltariam {pts(plan.missing)} pontos.</b>"
    else:
        txt += " ✅ Dá para emitir com o que você já tem."
    return txt


def _airlines(t: Trip) -> str:
    names = {"AD": "Azul", "LA": "LATAM", "G3": "GOL", "JJ": "LATAM", "2Z": "Voepass"}
    cias = {names.get(x, x) for x in (t.out.airline, t.back.airline) if x}
    return " / ".join(sorted(cias))


def _calendars(title: str, by_day: dict[date, Offer], points: bool, open_: bool = False) -> str:
    if not by_day:
        return ""
    value = (lambda o: o.points) if points else (lambda o: o.price)
    level = an.price_levels([value(o) for o in by_day.values()])
    months = sorted({(d.year, d.month) for d in by_day})
    cals = []
    for (y, m) in months:
        cells = [f"<div class='wd'>{w}</div>" for w in WEEKDAYS]
        first_wd, ndays = calendar.monthrange(y, m)
        cells += ["<div class='day empty'></div>"] * first_wd
        for day in range(1, ndays + 1):
            o = by_day.get(date(y, m, day))
            if o is None:
                cells.append(f"<div class='day'><i>{day}</i></div>")
                continue
            v = value(o)
            txt = kpts(v) if points else brl(v).replace("R$ ", "")
            tip = f"{day:02d}/{m:02d}: " + (f"{pts(v)} pontos + {brl(o.price)}" if points else brl(v))
            cells.append(f"<div class='day lv{level(v)}' title='{escape(tip, quote=True)}'><i>{day}</i><b>{txt}</b></div>")
        cals.append(f"<div class='cal'><h4>{MONTHS[m]} {y}</h4><div class='grid'>{''.join(cells)}</div></div>")
    legend = ("<div class='legend'>mais barato <span class='lv0'></span><span class='lv1'></span><span class='lv2'>"
              "</span><span class='lv3'></span><span class='lv4'></span> mais caro · cinza = sem dado"
              + (" · valores em R$ (só ida)" if not points else " · valores em mil pontos (só ida)") + "</div>")
    return (f"<details{' open' if open_ else ''}><summary>{escape(title)}</summary>{legend}"
            f"<div class='months'>{''.join(cals)}</div></details>")


# ------------------------------------------------------------------ qualquer destino

def _anywhere(rep: Report) -> str:
    cfg = rep.cfg
    out = [f"<section class='card' id='oportunidades'><h2>Oportunidades saindo de {escape(city(cfg.origin))}</h2>",
           f"<div class='muted small'>Ida e volta mais baratas para qualquer destino nos próximos "
           f"{cfg.anywhere_months} meses.</div>"]
    if rep.deals:
        rows = []
        for dl in rep.deals:
            nights = f"{dl.nights}" if dl.nights is not None else "—"
            ret = dm(dl.ret) if dl.ret else "só ida"
            hot = cfg.anywhere_max_price and dl.price <= cfg.anywhere_max_price
            rows.append(
                f"<tr class='{'best' if hot else ''}'><td>{escape(label(dl.destination))}{' 🔥' if hot else ''}</td>"
                f"<td>{dm(dl.depart)}</td><td>{ret}</td><td class='num'>{nights}</td><td class='num'>{brl(dl.price)}</td>"
                f"<td>{a(dl.link or links.google_flights(cfg.origin, dl.destination, dl.depart, dl.ret), 'Ver')} · "
                f"{a(links.google_flights(cfg.origin, dl.destination, dl.depart, dl.ret), 'Google Voos')}</td></tr>")
        out.append("<div class='scroll'><table><thead><tr><th>Destino</th><th>Ida</th><th>Volta</th><th>Noites</th>"
                   "<th>Total</th><th>Links</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")
        if cfg.anywhere_max_price:
            out.append(f"<p class='small muted'>🔥 = abaixo de {brl(cfg.anywhere_max_price)} (você é avisado).</p>")
    else:
        out.append("<p class='muted'>Sem ofertas em cache no momento.</p>")
    if rep.award_deals:
        rows = []
        for o in rep.award_deals:
            rows.append(f"<tr><td>{escape(label(o.destination))}</td><td>{dm(o.day)}</td>"
                        f"<td class='num'>{pts(o.points)}</td><td class='num'>{brl(o.price)}</td>"
                        f"<td>{a(links.azul(o.origin, o.destination, o.day, points=True), 'Azul (pontos)')}</td></tr>")
        out.append("<h3>Resgates Azul mais baratos (só ida)</h3><div class='scroll'><table><thead><tr><th>Destino</th>"
                   "<th>Data</th><th>Pontos</th><th>Taxas</th><th>Conferir</th></tr></thead><tbody>"
                   + "".join(rows) + "</tbody></table></div>")
    out.append("</section>")
    return "".join(out)


def _promos(rep: Report) -> str:
    out = ["<section class='card' id='promocoes'><h2>Promoções recentes</h2>"]
    if rep.promos:
        items = []
        for p in rep.promos:
            tag = "bônus transferência" if p.kind == "transferencia" else "passagem"
            when = p.published.strftime("%d/%m") if p.published else ""
            items.append(f"<li><span class='tag'>{tag}</span> {a(p.link, p.title)} "
                         f"<span class='muted small'>{escape(p.source)} {when}</span></li>")
        out.append("<ul class='promos'>" + "".join(items) + "</ul>")
    else:
        out.append("<p class='muted'>Nada relevante nos últimos dias.</p>")
    out.append("</section>")
    return "".join(out)


def _footer(rep: Report) -> str:
    return ("<p class='muted small'>Preços em dinheiro vêm de buscas recentes (cache da Aviasales) e podem ter mudado; "
            "pontos vêm do Seats.aero. Sempre confira no site da companhia antes de comprar ou transferir pontos — "
            "transferências são irreversíveis.</p>")
