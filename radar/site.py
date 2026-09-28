"""Gera o painel em HTML estático (um arquivo só, sem JavaScript obrigatório)."""
from __future__ import annotations

import calendar
from datetime import date
from html import escape

from radar import analysis as an
from radar import links
from radar.airports import city, label
from radar.engine import Report, RouteReport
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
.kpi b{display:block;font-size:1.3rem}.kpi span{display:block;color:var(--muted);font-size:.85rem}
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

    main = rr.main
    if not main.out_cash and not rr.out_award:
        out.append("<p class='muted'>Sem dados de preço para essa rota agora. Veja os avisos no fim da página.</p>"
                   "</section>")
        return "".join(out)

    for w in cfg.windows:
        out.append(_window(rep, rr, w))

    n = main.group.size
    who = f"por pessoa, {escape(main.group.name)}" if n > 1 else "R$"
    out.append(_calendars(f"Calendário de preços — ida ({city(o)} → {city(d)})", main.out_cash, False,
                          open_=True, divisor=n, unit=who))
    out.append(_calendars(f"Calendário de preços — volta ({city(d)} → {city(o)})", main.back_cash, False,
                          divisor=n, unit=who))
    if rr.out_award or rr.back_award:
        out.append(_calendars(f"Calendário em pontos Azul — ida ({city(o)} → {city(d)})", rr.out_award, True))
        out.append(_calendars(f"Calendário em pontos Azul — volta ({city(d)} → {city(o)})", rr.back_award, True))
    out.append("</section>")
    return "".join(out)


def _group_box(g, t: Trip) -> str:
    n = g.size
    per = f"<span>{brl(t.total_price / n)} por pessoa</span>" if n > 1 else ""
    return (f"<div class='kpi'><span>{escape(g.name)} · {escape(g.label)}</span><b>{brl(t.total_price)}</b>{per}"
            f"<span>{dm(t.out.day)} → {dm(t.back.day)} · {t.nights} noites</span></div>")


def _trips_table(cfg, r, g, trips: list[Trip]) -> str:
    o, d, n = cfg.origin, r.destination, g.size
    rows = []
    for i, t in enumerate(trips):
        rows.append(
            f"<tr class='{'best' if i == 0 else ''}'><td>{dm(t.out.day)} → {dm(t.back.day)}</td>"
            f"<td class='num'>{t.nights}</td>"
            + (f"<td class='num'>{brl(t.total_price / n)}</td>" if n > 1 else "")
            + f"<td class='num'>{brl(t.total_price)}</td>"
            f"<td>{a(links.google_flights(o, d, t.out.day, t.back.day, g.adults, g.children), 'Google Voos')} · "
            f"{a(links.azul(o, d, t.out.day, t.back.day, False, g.adults, g.children), 'Azul')}</td></tr>")
    head = ("<tr><th>Ida → volta</th><th>Noites</th>" + ("<th>Por pessoa</th>" if n > 1 else "")
            + "<th>Total</th><th>Conferir</th></tr>")
    return ("<div class='scroll'><table><thead>" + head + "</thead><tbody>" + "".join(rows)
            + "</tbody></table></div>")


def _window(rep: Report, rr: RouteReport, w) -> str:
    cfg, r = rep.cfg, rr.route
    out = [f"<h3>{escape(w.name)} <span class='tag'>{w.start:%d/%m/%y} a {w.end:%d/%m/%y} · "
           f"{w.min_stay}–{w.max_stay} noites</span></h3>"]
    boxes = [(gr, gr.trips.get(w.name) or []) for gr in rr.groups]
    if any(trips for _, trips in boxes):
        out.append("<div class='kpis'>" + "".join(_group_box(gr.group, trips[0]) for gr, trips in boxes if trips)
                   + "</div>")
        for i, (gr, trips) in enumerate(boxes):
            if not trips:
                continue
            title = f"Melhores datas para {escape(gr.group.name)} ({escape(gr.group.label)})"
            out.append(f"<details{' open' if i == 0 else ''}><summary>{title}</summary>"
                       + _trips_table(cfg, r, gr.group, trips) + "</details>")
    else:
        out.append("<p class='muted small'>Sem combinação em dinheiro com dados suficientes nessa janela.</p>")

    pw = next((p for p in rr.points if p.window.name == w.name), None)
    if pw and pw.award:
        out.append(_award_table(rep, rr, pw.award))
    elif pw and pw.azul and rep.calibration:
        out.append(_points_estimate(rep, rr, pw.azul[0]))
    return "".join(out)


def _points_per_group(rep: Report, per_person: int) -> str:
    return " · ".join(f"{escape(g.name)}: <b>{pts(per_person * g.size)}</b>" for g in rep.cfg.groups)


def _points_estimate(rep: Report, rr: RouteReport, t: Trip) -> str:
    """Estimativa de pontos a partir do preço da própria Azul em R$."""
    cfg, cal = rep.cfg, rep.calibration
    pp = cal.estimate(t.total_price)
    if cal.calibrated:
        how = (f"calibrada com {cal.samples_used} anotação(ões) suas do site da Azul: "
               f"R$ 1 ≈ {cal.points_per_real:.0f} pontos")
    else:
        how = (f"régua padrão de R$ {cfg.point_value:.0f} por 1.000 pontos — anote preços do site da Azul em "
               f"<code>pontos_azul.yaml</code> para calibrar")
    main = cfg.main_group
    plan = an.plan_points(cfg, pp * main.size, rep.bonus_pcts)
    return (f"<div class='good'>🔵 <b>Em pontos Azul (estimativa):</b> cerca de <b>{pts(pp)} pontos por pessoa</b> "
            f"— {_points_per_group(rep, pp)}.<br><span class='small'>Baseado na passagem mais barata da Azul em R$ "
            f"({brl(t.total_price)}/pessoa, {dm(t.out.day)} → {dm(t.back.day)}); {how}.</span><br>"
            f"<span class='small'>Para {escape(main.name)}: {_plan_text(cfg, plan)}</span></div>")


def _award_table(rep: Report, rr: RouteReport, trips: list[Trip]) -> str:
    cfg, r = rep.cfg, rr.route
    o, d = cfg.origin, r.destination
    main = cfg.main_group
    best = trips[0]
    taxes = best.out.price + best.back.price
    plan = an.plan_points(cfg, best.total_points * main.size, rep.bonus_pcts)
    lines = [f"🔵 Mais barato em pontos: <b>{pts(best.total_points)} pontos Azul por pessoa</b> + {brl(taxes)} de "
             f"taxas — {dm(best.out.day)} → {dm(best.back.day)} ({best.nights} noites).",
             _points_per_group(rep, best.total_points) + "."]
    cash_same = _azul_cash_for(rr, best)
    if cash_same:
        v = an.value_per_thousand(cash_same, best.total_points, taxes)
        if v:
            verdict = "✅ vale usar pontos" if v >= cfg.point_value else "💸 melhor pagar em dinheiro"
            lines.append(f"Nas mesmas datas, a Azul em dinheiro sai {brl(cash_same)}/pessoa → cada 1.000 pontos "
                         f"valem <b>R$ {v:.2f}</b> ({verdict}; sua régua é R$ {cfg.point_value:.0f}).")
    lines.append(f"Para {escape(main.name)}: " + _plan_text(cfg, plan))
    rows = []
    for i, t in enumerate(trips):
        rows.append(
            f"<tr class='{'best' if i == 0 else ''}'><td>{dm(t.out.day)}</td><td>{dm(t.back.day)}</td>"
            f"<td class='num'>{t.nights}</td><td class='num'>{pts(t.total_points)}</td>"
            f"<td class='num'>{pts(t.total_points * main.size)}</td><td class='num'>{brl(t.out.price + t.back.price)}</td>"
            f"<td>{a(links.azul(o, d, t.out.day, t.back.day, True, main.adults, main.children), 'Azul (pontos)')}"
            f"</td></tr>")
    return ("<div class='good'>" + "<br>".join(lines) + "</div>"
            "<div class='scroll'><table><thead><tr><th>Ida</th><th>Volta</th><th>Noites</th><th>Pts/pessoa</th>"
            f"<th>Pts {escape(main.name)}</th><th>Taxas/pessoa</th><th>Conferir</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")


def _azul_cash_for(rr: RouteReport, t: Trip) -> float | None:
    o, b = rr.azul_out.get(t.out.day), rr.azul_back.get(t.back.day)
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


def _calendars(title: str, by_day: dict[date, Offer], points: bool, open_: bool = False,
               divisor: int = 1, unit: str = "R$") -> str:
    if not by_day:
        return ""
    value = (lambda o: o.points) if points else (lambda o: o.price / divisor)
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
            tip += f" · {o.provider}" if o.provider else ""
            cells.append(f"<div class='day lv{level(v)}' title='{escape(tip, quote=True)}'><i>{day}</i><b>{txt}</b></div>")
        cals.append(f"<div class='cal'><h4>{MONTHS[m]} {y}</h4><div class='grid'>{''.join(cells)}</div></div>")
    legend = ("<div class='legend'>mais barato <span class='lv0'></span><span class='lv1'></span><span class='lv2'>"
              "</span><span class='lv3'></span><span class='lv4'></span> mais caro · cinza = sem dado"
              + (f" · valores em R$ {unit} (só ida)" if not points else " · mil pontos por pessoa (só ida)")
              + "</div>")
    return (f"<details{' open' if open_ else ''}><summary>{escape(title)}</summary>{legend}"
            f"<div class='months'>{''.join(cals)}</div></details>")


# ------------------------------------------------------------------ qualquer destino

def _anywhere(rep: Report) -> str:
    cfg = rep.cfg
    g = cfg.main_group
    multi = g.size > 1
    out = [f"<section class='card' id='oportunidades'><h2>Oportunidades saindo de {escape(city(cfg.origin))}</h2>",
           f"<div class='muted small'>Ida e volta mais baratas nos próximos {cfg.anywhere_months} meses, "
           f"{cfg.anywhere_min_stay} a {cfg.anywhere_max_stay} noites"
           + (f", preços para {escape(g.name)} ({escape(g.label)})" if multi else "")
           + f". Cada rodada confere {cfg.anywhere_max_dest} destinos em rodízio; a coluna \"Visto\" diz quando "
           "o preço foi conferido.</div>"]
    if rep.deals:
        rows = []
        for dl in rep.deals:
            nights = f"{dl.nights}" if dl.nights is not None else "—"
            ret = dm(dl.ret) if dl.ret else "só ida"
            hot = cfg.anywhere_max_price and dl.per_person <= cfg.anywhere_max_price
            seen = rep.deals_checked.get(dl.destination)
            seen_txt = "hoje" if seen == rep.today else (seen.strftime("%d/%m") if seen else "")
            rows.append(
                f"<tr class='{'best' if hot else ''}'><td>{escape(label(dl.destination))}{' 🔥' if hot else ''}</td>"
                f"<td class='num'>{brl(dl.per_person)}</td><td>{dm(dl.depart)} → {ret}</td>"
                f"<td class='num'>{nights}</td>"
                + (f"<td class='num'>{brl(dl.price)}</td>" if multi else "")
                + f"<td class='muted'>{escape(dl.provider)}</td><td class='muted'>{seen_txt}</td>"
                f"<td>{_deal_links(cfg, dl)}</td></tr>")
        head = ("<tr><th>Destino</th><th>Por pessoa</th><th>Ida → volta</th><th>Noites</th>"
                + (f"<th>Total {escape(g.name)}</th>" if multi else "")
                + "<th>Fonte</th><th>Visto</th><th>Conferir</th></tr>")
        out.append("<div class='scroll'><table><thead>" + head + "</thead><tbody>" + "".join(rows)
                   + "</tbody></table></div>")
        if cfg.anywhere_max_price:
            out.append(f"<p class='small muted'>🔥 = abaixo de {brl(cfg.anywhere_max_price)} por pessoa "
                       "(você é avisado).</p>")
    else:
        out.append("<p class='muted'>Sem ofertas no momento.</p>")
    if rep.award_deals:
        rows = []
        for o in rep.award_deals:
            rows.append(f"<tr><td>{escape(label(o.destination))}</td><td>{dm(o.day)}</td>"
                        f"<td class='num'>{pts(o.points)}</td><td class='num'>{brl(o.price)}</td>"
                        f"<td>{a(links.azul(o.origin, o.destination, o.day, points=True), 'Azul (pontos)')}</td></tr>")
        out.append("<h3>Resgates Azul mais baratos (só ida, por pessoa)</h3><div class='scroll'><table><thead><tr>"
                   "<th>Destino</th><th>Data</th><th>Pontos</th><th>Taxas</th><th>Conferir</th></tr></thead><tbody>"
                   + "".join(rows) + "</tbody></table></div>")
    out.append("</section>")
    return "".join(out)


def _deal_links(cfg, dl) -> str:
    g = cfg.main_group
    google = a(links.google_flights(cfg.origin, dl.destination, dl.depart, dl.ret, g.adults, g.children),
               "Google Voos")
    if dl.link and "google.com" not in dl.link:
        return a(dl.link, "Oferta") + " · " + google
    return google


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
    counts = ", ".join(f"{escape(k)} ({v} preços)" for k, v in rep.source_counts.items()) or "nenhuma"
    return (f"<p class='muted small'>Fontes desta atualização: {counts}. Preços em R$ combinam o Google Voos "
            "(menor preço de cada dia) com o cache de buscas da Travelpayouts/Aviasales; em cada dia vale o mais "
            "barato. Pontos vêm do Seats.aero quando configurado. Sempre confira no site da companhia antes de "
            "comprar ou transferir pontos — transferências são irreversíveis.</p>")
