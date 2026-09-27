"""Cálculos: menor preço por dia, melhores combinações ida/volta e contas de pontos."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from radar.config import Config, Program
from radar.models import Deal, Offer, Trip


def cash_key(o: Offer) -> float:
    return o.price


def points_key(o: Offer) -> float:
    return o.points + o.price / 1000  # desempate pelas taxas


def cheapest_by_day(offers: Iterable[Offer], key: Callable[[Offer], float] = cash_key) -> dict[date, Offer]:
    best: dict[date, Offer] = {}
    for o in offers:
        cur = best.get(o.day)
        if cur is None or key(o) < key(cur):
            best[o.day] = o
    return best


def best_round_trips(
    outs: dict[date, Offer],
    backs: dict[date, Offer],
    start: date,
    end: date,
    min_stay: int,
    max_stay: int,
    *,
    points: bool = False,
    extra_cost: float = 0.0,
    top: int = 8,
) -> list[Trip]:
    """Melhores idas/voltas com ida >= start, volta <= end e estadia entre min e max noites.

    Garante variedade: no máximo uma sugestão por data de ida.
    """
    per_out: list[Trip] = []
    for d_out, o in outs.items():
        if not start <= d_out <= end:
            continue
        best: Trip | None = None
        for n in range(min_stay, max_stay + 1):
            d_back = d_out + timedelta(days=n)
            if d_back > end:
                break
            b = backs.get(d_back)
            if b is None:
                continue
            t = Trip(o, b, extra_cost)
            if best is None or _trip_key(t, points) < _trip_key(best, points):
                best = t
        if best:
            per_out.append(best)
    per_out.sort(key=lambda t: _trip_key(t, points))
    return per_out[:top]


def _trip_key(t: Trip, points: bool) -> tuple:
    return (t.total_points, t.total_price) if points else (t.total_price, -t.nights)


def price_levels(values: list[float], buckets: int = 5) -> Callable[[float], int]:
    """Função que devolve o nível 0 (mais barato) .. buckets-1 (mais caro) por quantil."""
    if not values:
        return lambda v: 0
    vals = sorted(values)
    cuts = [vals[max(0, int(len(vals) * i / buckets) - 1)] for i in range(1, buckets)]

    def level(v: float) -> int:
        return sum(v > c for c in cuts)

    return level


# ---------------------------------------------------------------- pontos

@dataclass(frozen=True)
class TransferStep:
    program: Program
    source_points: int      # quanto sai do programa de origem
    azul_points: int        # quanto chega na Azul (com bônus)
    bonus: float


@dataclass(frozen=True)
class PointsPlan:
    needed: int
    from_azul: int
    transfers: tuple[TransferStep, ...]
    missing: int            # pontos Azul que ainda faltariam

    @property
    def feasible(self) -> bool:
        return self.missing == 0


def azul_power(cfg: Config, bonuses: dict[str, float] | None = None) -> int:
    """Total de pontos Azul que você conseguiria juntar transferindo tudo."""
    bonuses = bonuses or {}
    total = cfg.balances.get("azul", 0)
    for key, prog in cfg.programs.items():
        b = bonuses.get(key, prog.bonus)
        total += int(cfg.balances.get(key, 0) * prog.ratio * (1 + b / 100))
    return total


def plan_points(cfg: Config, needed: int, bonuses: dict[str, float] | None = None) -> PointsPlan:
    """Usa primeiro os pontos Azul e depois transfere dos programas com maior bônus."""
    bonuses = bonuses or {}
    from_azul = min(needed, cfg.balances.get("azul", 0))
    remaining = needed - from_azul
    steps = []
    progs = sorted(cfg.programs.values(), key=lambda p: -(bonuses.get(p.key, p.bonus)))
    for prog in progs:
        if remaining <= 0:
            break
        bal = cfg.balances.get(prog.key, 0)
        b = bonuses.get(prog.key, prog.bonus)
        rate = prog.ratio * (1 + b / 100)
        if bal <= 0 or rate <= 0:
            continue
        src = min(bal, -(-remaining // rate))  # arredonda para cima
        src = int(src)
        got = int(src * rate)
        steps.append(TransferStep(prog, src, got, b))
        remaining -= got
    return PointsPlan(needed, from_azul, tuple(steps), max(0, remaining))


def value_per_thousand(cash_price: float, points: int, taxes: float) -> float | None:
    """Quanto cada 1.000 pontos 'rendem' em R$ nessa troca (quanto maior, melhor)."""
    if points <= 0 or cash_price <= 0:
        return None
    return round((cash_price - taxes) / points * 1000, 2)


def estimate_points(cash_price: float, point_value: float) -> int:
    return int(round(cash_price / point_value * 1000, -2))


# ---------------------------------------------------------------- qualquer destino

def best_deals(deals: Iterable[Deal], exclude: Iterable[str] = (), top: int = 20) -> list[Deal]:
    """Menor preço por destino, ordenado do mais barato."""
    excl = {e.upper() for e in exclude}
    best: dict[str, Deal] = {}
    for d in deals:
        if not d.destination or d.destination in excl or d.destination == d.origin:
            continue
        if d.destination not in best or d.price < best[d.destination].price:
            best[d.destination] = d
    return sorted(best.values(), key=lambda d: d.price)[:top]


def best_awards_anywhere(offers: Iterable[Offer], exclude: Iterable[str] = (), top: int = 15) -> list[Offer]:
    excl = {e.upper() for e in exclude}
    best: dict[str, Offer] = {}
    for o in offers:
        if o.destination in excl:
            continue
        if o.destination not in best or points_key(o) < points_key(best[o.destination]):
            best[o.destination] = o
    return sorted(best.values(), key=points_key)[:top]
