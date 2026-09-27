from datetime import date

from radar.config import load_config
from radar.engine import build_report, compute_alerts
from radar.providers.demo import DemoAwardProvider, DemoCashProvider, DemoPromoProvider
from radar.site import render

TODAY = date(2026, 9, 27)


def report(tmp_config="config.yaml"):
    cfg = load_config(tmp_config, TODAY)
    return build_report(cfg, DemoCashProvider(), DemoAwardProvider(), DemoPromoProvider(TODAY), TODAY, demo=True)


def test_report_has_routes_windows_and_no_past_dates():
    rep = report()
    assert [r.route.destination for r in rep.routes] == ["MCZ", "REC"]
    for rr in rep.routes:
        assert all(d > TODAY for d in rr.out_cash)
        for wr in rr.windows:
            assert wr.cash and wr.award
            for t in wr.cash:
                assert wr.window.start <= t.out.day and t.back.day <= wr.window.end
    rec = rep.routes[1]
    assert rec.windows[0].cash[0].extra_cost == 350
    assert rep.deals and rep.bonuses.get("livelo").bonus_pct == 100


def test_alerts_are_not_repeated():
    rep = report()
    state = {}
    first = compute_alerts(rep, state)
    assert any(a.key.startswith("promo|") for a in first)
    second = compute_alerts(report(), state)
    assert not [a for a in second if a.key.startswith(("promo|", "alvo|", "oport|"))]


def test_price_drop_alert():
    rep = report()
    state = {}
    key = f"BEL-MCZ|{rep.routes[0].windows[0].window.name}|brl"
    best = rep.routes[0].windows[0].cash[0].total_price
    state["history"] = {key: [{"t": "2026-09-20", "v": best * 2}]}
    alerts = compute_alerts(rep, state)
    assert any(a.key == f"queda|{key}" for a in alerts)


def test_render_html():
    html = render(report())
    assert "Radar de Passagens" in html and "Maceió" in html and "FICTÍCIOS" in html


def test_alert_priorities():
    from radar.engine import PRIORITY_LOW, PRIORITY_URGENT

    by_title = {a.title: a.priority for a in compute_alerts(report(), {})}
    assert by_title["💳 [EXEMPLO] Inter Loop: ganhe 80% de bônus ao transferir pontos para a Azul"] == PRIORITY_URGENT
    assert by_title["🏷️ [EXEMPLO] Passagens de Belém para Lima a partir de R$ 899 ida e volta"] == PRIORITY_LOW
    assert all(p == PRIORITY_URGENT for t, p in by_title.items() if "abaixo do alvo" in t)


def test_empty_route_is_reported():
    class Empty(DemoCashProvider):
        def one_way_month(self, *a):
            return []

    cfg = load_config("config.yaml", TODAY)
    rep = build_report(cfg, Empty(), None, None, TODAY)
    assert any("BEL⇄MCZ: nenhum preço" in e for e in rep.errors)
    assert "Sem dados de preço" in render(rep)
