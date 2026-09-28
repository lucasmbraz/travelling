from datetime import date, timedelta

from radar.config import Group, PointsSample, load_config
from radar.engine import (PRIORITY_LOW, PRIORITY_URGENT, build_report, compute_alerts)
from radar.models import Deal, Offer
from radar.providers.demo import DemoAwardProvider, DemoCashProvider, DemoPromoProvider
from radar.site import render

TODAY = date(2026, 9, 27)


def cfg():
    return load_config("config.yaml", TODAY)


def report(award=True, state=None, config=None):
    return build_report(config or cfg(), [DemoCashProvider()], DemoAwardProvider() if award else None,
                        DemoPromoProvider(TODAY), TODAY, demo=True, state=state)


class Source:
    """Fonte falsa: preço fixo por pessoa num único dia, somado para o grupo."""

    def __init__(self, name, price, day, fail=False):
        self.name, self.price, self.day, self.fail = name, price, day, fail
        self.calls = []

    def one_way_range(self, o, d, start, end, adults=1, children=0, airline=None):
        self.calls.append((o, d, adults, children, airline))
        if self.fail:
            raise RuntimeError("fora do ar")
        return [Offer(o, d, self.day, self.price * (adults + children), airline=airline or "", provider=self.name)]


def test_report_has_groups_windows_and_no_past_dates():
    rep = report()
    assert [r.route.destination for r in rep.routes] == ["MCZ", "REC"]
    for rr in rep.routes:
        assert [g.group.key for g in rr.groups] == ["adulto"]
        for gr in rr.groups:
            assert all(d > TODAY for d in gr.out_cash)
            for w in rep.cfg.windows:
                trips = gr.trips[w.name]
                assert trips
                for t in trips:
                    assert w.start <= t.out.day and t.back.day <= w.end
                    assert w.min_stay <= t.nights <= w.max_stay
        assert rr.azul_out and all(o.airline == "AD" for o in rr.azul_out.values())
    assert rep.routes[1].groups[0].trips[rep.cfg.windows[0].name][0].extra_cost == 0
    assert rep.bonuses.get("livelo").bonus_pct == 100


def test_flexible_window_is_5_to_21_nights():
    w = next(w for w in cfg().windows if w.name.startswith("Próximos"))
    assert (w.min_stay, w.max_stay) == (5, 21)


def family_cfg():
    c = cfg()
    c.groups = [Group("familia", "Família", 2, 3), Group("casal", "Casal", 2, 0)]
    return c


def test_default_is_one_adult():
    c = cfg()
    assert [(g.adults, g.children) for g in c.groups] == [(1, 0)]


def test_groups_are_searched_with_their_passengers():
    day = TODAY + timedelta(days=80)
    src = Source("A", 500, day)
    rep = build_report(family_cfg(), [src], None, None, TODAY)
    pax = {(a, c, al) for (_, _, a, c, al) in src.calls}
    assert {(2, 3, None), (2, 0, None), (1, 0, "AD")} <= pax
    mcz = rep.routes[0]
    assert mcz.groups[0].out_cash[day].price == 2500  # família: 5 × 500
    assert mcz.groups[1].out_cash[day].price == 1000  # casal: 2 × 500
    assert mcz.azul_out[day].price == 500             # só Azul, 1 pessoa (base dos pontos)


def test_sources_are_combined_cheapest_wins_and_failures_are_isolated():
    day = TODAY + timedelta(days=80)
    sources = [Source("A", 700, day), Source("B", 500, day), Source("C", 0, day, fail=True)]
    rep = build_report(cfg(), sources, None, None, TODAY)
    main = rep.routes[0].main
    assert main.out_cash[day].price == 500 and main.out_cash[day].provider == "B"
    assert any(e.startswith("C BEL→MCZ: fora do ar") for e in rep.errors)
    assert rep.source_counts["A"] > 0 and rep.source_counts["B"] > 0


def test_points_calibration_uses_samples():
    c = cfg()
    rep0 = report(award=False, config=c)
    rr = rep0.routes[0]
    day, off = next(iter(rr.azul_out.items()))
    assert not rep0.calibration.calibrated
    assert rep0.calibration.points_per_real == 1000 / c.point_value
    # anotação sem R$: usa o preço da Azul do mesmo dia; com R$: usa o informado
    c.points_samples = [PointsSample("BEL", "MCZ", day, points=int(off.price * 50)),
                        PointsSample("MCZ", "BEL", day, points=30000, cash=600)]
    rep = report(award=False, config=c)
    assert rep.calibration.samples_used == 2
    assert 49 < rep.calibration.points_per_real <= 50
    html = render(rep)
    assert "Em pontos Azul (estimativa)" in html and "calibrada com 2 anotação" in html
    assert "Plano:" in html or "saldos" in html


def test_anywhere_rotates_and_keeps_recent_results():
    state = {}
    c = cfg()
    rep1 = report(state=state, config=c)
    first = set(state["anywhere"]["deals"])
    assert len(first) >= c.anywhere_max_dest - 2  # alguns podem não ter volta
    assert state["anywhere"]["offset"] == c.anywhere_max_dest
    rep2 = report(state=state, config=c)
    second_batch = {d for d, j in state["anywhere"]["deals"].items() if d not in first}
    assert second_batch  # a segunda rodada conferiu outros destinos
    shown = {d.destination for d in rep2.deals}
    assert len(shown) >= len({d.destination for d in rep1.deals})
    assert all(d.pax == 1 for d in rep2.deals)


def test_anywhere_cache_expires():
    state = {"anywhere": {"offset": 0, "deals": {"LIS": {
        "dest": "LIS", "depart": "2026-11-01", "ret": "2026-11-08", "price": 20000.0, "pax": 5,
        "provider": "x", "link": "", "checked": (TODAY - timedelta(days=10)).isoformat()}}}}
    report(state=state)
    assert state["anywhere"]["deals"].get("LIS", {}).get("checked") != (TODAY - timedelta(days=10)).isoformat()


def test_alerts_are_per_person_and_not_repeated():
    state = {}
    first = compute_alerts(report(), state)
    assert any(a.key.startswith("promo|") for a in first)
    alvo = [a for a in first if a.key.startswith("alvo|") and a.key.endswith("|adulto|pp")]
    assert alvo and "/pessoa" in alvo[0].text
    second = compute_alerts(report(), state)
    assert not [a for a in second if a.key.startswith(("promo|", "alvo|", "oport|"))]


def test_old_history_keys_are_dropped():
    state = {"history": {"BEL-MCZ|Fim de ano|brl": [{"t": "2026-09-20", "v": 1}],
                         "BEL-FOR|qualquer": [{"t": "2026-09-20", "v": 1}]}}
    compute_alerts(report(), state)
    assert "BEL-MCZ|Fim de ano|brl" not in state["history"] and "BEL-FOR|qualquer" not in state["history"]


def test_price_drop_alert():
    rep = report()
    w = rep.cfg.windows[0]
    key = f"BEL-MCZ|{w.name}|adulto|pp"
    best_pp = rep.routes[0].main.trips[w.name][0].total_price
    state = {"history": {key: [{"t": "2026-09-20", "v": best_pp * 2}]}, "alerted": {}}
    state["alerted"][key] = best_pp  # alvo já avisado com esse preço: sobra o alerta de queda
    alerts = compute_alerts(rep, state)
    assert any(a.key == f"queda|{key}" for a in alerts)


def test_alert_priorities():
    by_title = {a.title: a.priority for a in compute_alerts(report(), {})}
    assert by_title["💳 [EXEMPLO] Inter Loop: ganhe 80% de bônus ao transferir pontos para a Azul"] == PRIORITY_URGENT
    assert by_title["🏷️ [EXEMPLO] Passagens de Belém para Lima a partir de R$ 899 ida e volta"] == PRIORITY_LOW
    assert all(p == PRIORITY_URGENT for t, p in by_title.items() if "abaixo do alvo" in t)


def test_empty_route_is_reported():
    class Empty(DemoCashProvider):
        def one_way_range(self, *a, **k):
            return []

    rep = build_report(cfg(), [Empty()], None, None, TODAY)
    assert any("BEL⇄MCZ: nenhum preço" in e for e in rep.errors)
    assert "Sem dados de preço" in render(rep)


def test_render_html():
    html = render(report())
    assert "Radar de Passagens" in html and "Maceió" in html and "FICTÍCIOS" in html
    assert "casa dos pais" not in html and "Ida e volta, 1 adulto" in html


def test_deal_per_person():
    d = Deal("BEL", "FOR", TODAY, None, 2500, pax=5)
    assert d.per_person == 500


def test_route_destinations_are_not_repeated_in_opportunities():
    dests = {d.destination for d in report().deals}
    assert "MCZ" not in dests and "REC" not in dests


def test_family_groups_still_render_per_person():
    html = render(build_report(family_cfg(), [DemoCashProvider()], None, None, TODAY, demo=True))
    assert "Por pessoa" in html and "Casal" in html and "Família: <b>" in html


def test_points_estimate_falls_back_when_no_azul_only_price():
    class NoAzul(DemoCashProvider):
        def one_way_range(self, *a, airline=None, **k):
            return [] if airline else super().one_way_range(*a, **k)

    html = render(build_report(cfg(), [NoAzul()], None, None, TODAY, demo=True))
    assert "Em pontos Azul (estimativa)" in html and "não achei preço só da Azul" in html
