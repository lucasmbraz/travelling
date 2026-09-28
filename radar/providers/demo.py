"""Dados FICTÍCIOS e determinísticos para testar o app sem chaves de API."""
from __future__ import annotations

import calendar
import hashlib
from dataclasses import replace
from datetime import date, timedelta

from radar.models import Deal, Offer, Promo

BASE_PRICE = {"MCZ": 520, "REC": 410, "FOR": 380, "GRU": 450, "LIM": 1150, "MIA": 1900,
              "LIS": 2900, "SSA": 470, "BSB": 360, "GIG": 500, "MAO": 390, "EZE": 1600,
              "CNF": 470, "SLZ": 260, "BOG": 1400, "PTY": 1500}
AIRLINES = ["AD", "LA", "G3"]


def _noise(*parts) -> float:
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:4], "big") / 2**32


def _season(d: date) -> float:
    if (d.month == 12 and d.day >= 18) or (d.month == 1 and d.day <= 6):
        return 1.9
    if d.month in (7, 1):
        return 1.35
    return 1.0


def demo_price(origin: str, dest: str, d: date) -> float:
    base = BASE_PRICE.get(dest, BASE_PRICE.get(origin, 600))
    weekday = 1.15 if d.weekday() in (4, 6) else 0.9 if d.weekday() in (1, 2) else 1.0
    return round(base * _season(d) * weekday * (0.7 + 0.8 * _noise(origin, dest, d)), 0)


class DemoCashProvider:
    name = "demo"
    calendar = True

    def one_way_month(self, origin: str, destination: str, year: int, month: int) -> list[Offer]:
        days = calendar.monthrange(year, month)[1]
        out = []
        for day in range(1, days + 1):
            d = date(year, month, day)
            if _noise("gap", origin, destination, d) < 0.12:  # dias sem dados, como no mundo real
                continue
            out.append(Offer(origin, destination, d, demo_price(origin, destination, d),
                             airline=AIRLINES[int(_noise("al", d) * 3)], transfers=int(_noise("tr", d) * 2),
                             link="https://www.aviasales.com", provider=self.name))
        return out

    def one_way_range(self, origin: str, destination: str, start: date, end: date,
                      adults: int = 1, children: int = 0, airline: str | None = None) -> list[Offer]:
        out, y, m = [], start.year, start.month
        while (y, m) <= (end.year, end.month):
            out += self.one_way_month(origin, destination, y, m)
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        n = adults + children
        # grupos grandes às vezes não cabem na tarifa mais barata
        bump = 1.0 if n <= 2 else 1.08
        out = [replace(o, price=round(o.price * n * (bump if _noise("pax", o.day) > 0.6 else 1.0)),
                       airline=airline or o.airline) for o in out if start <= o.day <= end]
        if airline:
            out = [replace(o, price=round(o.price * 1.05)) for o in out]  # só a Azul: um pouco mais caro
        return out

    def anywhere_month(self, origin: str, year: int, month: int) -> list[Deal]:
        deals = []
        for dest in BASE_PRICE:
            if dest == origin:
                continue
            dep = date(year, month, 1 + int(_noise("dep", dest, month) * 27))
            ret = dep + timedelta(days=3 + int(_noise("ret", dest, month) * 10))
            price = demo_price(origin, dest, dep) + demo_price(dest, origin, ret)
            if _noise("cheap", dest, month) > 0.8:
                price *= 0.55  # "promoção relâmpago"
            deals.append(Deal(origin, dest, dep, ret, round(price), AIRLINES[int(_noise("a", dest) * 3)],
                              link="https://www.aviasales.com", provider=self.name))
        return deals


class DemoAwardProvider:
    name = "demo"

    def _award(self, origin: str, dest: str, d: date) -> Offer | None:
        if _noise("award", origin, dest, d) < 0.35:
            return None
        pts = demo_price(origin, dest, d) / 16 * 1000 * (0.6 + 0.8 * _noise("pts", origin, dest, d))
        return Offer(origin, dest, d, price=38.0, points=int(round(pts, -2)), airline="AD",
                     transfers=0, link="https://seats.aero/azul", provider=self.name)

    def one_way(self, origin: str, destinations: list[str], start: date, end: date) -> list[Offer]:
        out, d = [], start
        while d <= end:
            out.extend(o for o in (self._award(origin, dest, d) for dest in destinations) if o)
            d += timedelta(days=1)
        return out

    def anywhere(self, origin: str, start: date, end: date) -> list[Offer]:
        dests = ["REC", "FOR", "GRU", "SSA", "BSB", "CNF", "MAO", "MCZ"]
        return self.one_way(origin, dests, start, end)


class DemoPromoProvider:
    name = "demo"

    def __init__(self, today: date):
        self.today = today

    def fetch(self) -> tuple[list[Promo], list[str]]:
        t = self.today
        return [
            Promo("[EXEMPLO] Azul Fidelidade oferece até 100% de bônus nas transferências de pontos da Livelo",
                  "https://example.com/livelo-azul-100", t - timedelta(days=1), "exemplo", "transferencia",
                  100, ("azul", "livelo")),
            Promo("[EXEMPLO] Inter Loop: ganhe 80% de bônus ao transferir pontos para a Azul",
                  "https://example.com/inter-azul-80", t - timedelta(days=3), "exemplo", "transferencia",
                  80, ("azul", "inter")),
            Promo("[EXEMPLO] Passagens de Belém para Lima a partir de R$ 899 ida e volta",
                  "https://example.com/bel-lim", t - timedelta(days=2), "exemplo", "passagem", None, ()),
            Promo("[EXEMPLO] Smiles com 70% de bônus para cartões", "https://example.com/smiles",
                  t - timedelta(days=1), "exemplo", "transferencia", 70, ("smiles",)),
        ], []
