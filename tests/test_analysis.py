from datetime import date, timedelta

from radar import analysis as an
from radar.config import Config, Program
from radar.models import Offer


def offer(day, price=0.0, points=0, o="BEL", d="MCZ"):
    return Offer(o, d, day, price, points)


def cfg(**balances):
    return Config(origin="BEL", balances=balances, point_value=16,
                  programs={"livelo": Program("livelo", "Livelo"), "cartao": Program("cartao", "Inter", bonus=0)},
                  routes=[], windows=[])


def test_cheapest_by_day_keeps_minimum():
    d = date(2026, 12, 1)
    best = an.cheapest_by_day([offer(d, 500), offer(d, 300), offer(d + timedelta(1), 400)])
    assert best[d].price == 300 and len(best) == 2


def test_round_trips_respect_window_and_stay():
    base = date(2026, 12, 10)
    outs = {base + timedelta(i): offer(base + timedelta(i), 300 + i * 10) for i in range(10)}
    backs = {base + timedelta(i): offer(base + timedelta(i), 200, o="MCZ", d="BEL") for i in range(30)}
    trips = an.best_round_trips(outs, backs, base, base + timedelta(15), 7, 10)
    assert trips[0].out.day == base
    for t in trips:
        assert 7 <= t.nights <= 10
        assert t.back.day <= base + timedelta(15)
    assert len({t.out.day for t in trips}) == len(trips)  # uma sugestão por data de ida


def test_round_trips_points_and_extra_cost():
    d = date(2027, 1, 5)
    outs = {d: offer(d, 30, 10000)}
    backs = {d + timedelta(7): offer(d + timedelta(7), 30, 12000), d + timedelta(8): offer(d + timedelta(8), 30, 9000)}
    [t] = an.best_round_trips(outs, backs, d, d + timedelta(20), 5, 10, points=True, extra_cost=350)
    assert t.total_points == 19000 and t.total_price == 410


def test_plan_points_uses_azul_then_best_bonus():
    c = cfg(azul=10000, livelo=20000, cartao=20000)
    plan = an.plan_points(c, 30000, {"cartao": 100})
    assert plan.from_azul == 10000
    assert plan.transfers[0].program.key == "cartao" and plan.transfers[0].source_points == 10000
    assert plan.transfers[0].azul_points == 20000 and plan.feasible


def test_plan_points_reports_missing():
    plan = an.plan_points(cfg(azul=1000, livelo=0, cartao=0), 5000)
    assert plan.missing == 4000 and not plan.feasible


def test_azul_power_with_bonus():
    assert an.azul_power(cfg(azul=100, livelo=1000, cartao=0), {"livelo": 80}) == 1900


def test_value_per_thousand():
    assert an.value_per_thousand(1000, 50000, 100) == 18.0
    assert an.value_per_thousand(1000, 0, 0) is None


def test_price_levels():
    level = an.price_levels([100, 200, 300, 400, 500])
    assert level(100) == 0 and level(500) == 4
