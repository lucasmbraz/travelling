"""Preços em dinheiro via Travelpayouts / Aviasales Data API.

Os dados vêm do cache de buscas feitas por usuários da Aviasales nos últimos dias,
então nem todo dia terá preço — mas é gratuito e aceita mês inteiro e destino em
aberto, que é justamente o que os sites das companhias não deixam fazer.

Token grátis: https://www.travelpayouts.com/ → Perfil → API token.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

from radar.models import Deal, Offer
from radar.providers.http import get_json

BASE = "https://api.travelpayouts.com"
SITE = "https://www.aviasales.com"


def _day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return date.fromisoformat(value[:10])


def _link(path: str | None) -> str:
    if not path:
        return ""
    return path if path.startswith("http") else SITE + path


class TravelpayoutsProvider:
    name = "Travelpayouts"

    def __init__(self, token: str, market: str = "br", currency: str = "brl"):
        self.token = token
        self.market = market
        self.currency = currency
        self._cache: dict = {}  # a mesma rota é pedida para cada grupo de viajantes

    def _get(self, path: str, **params):
        params = {k: v for k, v in params.items() if v is not None}
        params.update(currency=self.currency, market=self.market)
        data = get_json(BASE + path, params=params, headers={"X-Access-Token": self.token})
        if isinstance(data, dict) and data.get("success") is False:
            raise RuntimeError(f"Travelpayouts: {data.get('error')}")
        return data.get("data") if isinstance(data, dict) else data

    def one_way_month(self, origin: str, destination: str, year: int, month: int) -> list[Offer]:
        """Trechos só de ida de um mês inteiro (vários por dia; o radar escolhe o menor)."""
        month_str = f"{year:04d}-{month:02d}"
        offers: list[Offer] = []

        rows = self._get(
            "/aviasales/v3/prices_for_dates",
            origin=origin, destination=destination, departure_at=month_str,
            one_way="true", sorting="price", limit=1000,
        ) or []
        for row in rows:
            offers.append(self._offer(row, origin, destination))

        # grouped_prices devolve o menor preço de cada dia; complementa o anterior.
        grouped = self._get(
            "/aviasales/v3/grouped_prices",
            origin=origin, destination=destination, departure_at=month_str,
            group_by="departure_at",
        ) or {}
        for row in (grouped.values() if isinstance(grouped, dict) else grouped):
            offers.append(self._offer(row, origin, destination))
        return [o for o in offers if o.day and o.price > 0]

    def one_way_range(self, origin: str, destination: str, start: date, end: date,
                      adults: int = 1, children: int = 0, airline: str | None = None) -> list[Offer]:
        """Preços do cache (sempre de 1 adulto). Para grupos, multiplica pelo número de
        pessoas e marca a fonte como estimada."""
        offers: list[Offer] = []
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            key = (origin, destination, y, m)
            if key not in self._cache:
                self._cache[key] = self.one_way_month(origin, destination, y, m)
            offers += self._cache[key]
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        offers = [o for o in offers if start <= o.day <= end and (not airline or o.airline == airline)]
        n = adults + children
        if n == 1:
            return offers
        return [replace(o, price=o.price * n, provider=f"{self.name} (×{n} estimado)") for o in offers]

    def _offer(self, row: dict, origin: str, destination: str) -> Offer:
        return Offer(
            origin=row.get("origin_airport") or row.get("origin") or origin,
            destination=row.get("destination_airport") or row.get("destination") or destination,
            day=_day(row.get("departure_at")),
            price=float(row.get("price") or row.get("value") or 0),
            airline=row.get("airline", ""),
            transfers=row.get("transfers"),
            link=_link(row.get("link")),
            provider=self.name,
        )

    def anywhere_month(self, origin: str, year: int, month: int) -> list[Deal]:
        """Ida e volta saindo de ``origin`` para qualquer destino em um mês."""
        rows = self._get(
            "/aviasales/v3/prices_for_dates",
            origin=origin, departure_at=f"{year:04d}-{month:02d}",
            one_way="false", sorting="price", unique="true", limit=1000,
        ) or []
        deals = []
        for row in rows:
            dep = _day(row.get("departure_at"))
            if not dep or not row.get("price"):
                continue
            deals.append(Deal(
                origin=row.get("origin_airport") or origin,
                destination=row.get("destination_airport") or row.get("destination", ""),
                depart=dep,
                ret=_day(row.get("return_at")),
                price=float(row["price"]),
                airline=row.get("airline", ""),
                transfers=row.get("transfers"),
                link=_link(row.get("link")),
                provider=self.name,
            ))
        return deals


# ---------------------------------------------------------------- diagnóstico

def _count(data) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        # alguns endpoints devolvem {destino: {...}} ou {data: {...}}
        return sum(_count(v) if isinstance(v, (dict, list)) and not {"price", "value"} & set(v) else 1
                   for v in data.values()) if data else 0
    return 0


def diagnose(token: str, origin: str, destinations: list[str], months: list[tuple[int, int]]) -> list[str]:
    """Roda variações de consulta para descobrir qual traz dados para as rotas."""

    hdr = {"X-Access-Token": token}
    lines = ["### Travelpayouts"]
    for dest in destinations:
        for o, d in ((origin, dest), (dest, origin)):
            for (y, m) in months:
                ym = f"{y:04d}-{m:02d}"
                variants = {
                    "v3 prices_for_dates só ida (market=br)": ("/aviasales/v3/prices_for_dates", dict(
                        origin=o, destination=d, departure_at=ym, one_way="true", sorting="price", limit=1000,
                        currency="brl", market="br")),
                    "v3 prices_for_dates só ida (sem market)": ("/aviasales/v3/prices_for_dates", dict(
                        origin=o, destination=d, departure_at=ym, one_way="true", sorting="price", limit=1000,
                        currency="brl")),
                    "v3 prices_for_dates ida e volta": ("/aviasales/v3/prices_for_dates", dict(
                        origin=o, destination=d, departure_at=ym, one_way="false", sorting="price", limit=1000,
                        currency="brl")),
                    "v3 grouped_prices por dia": ("/aviasales/v3/grouped_prices", dict(
                        origin=o, destination=d, departure_at=ym, group_by="departure_at", currency="brl")),
                    "v1 prices/calendar": ("/v1/prices/calendar", dict(
                        origin=o, destination=d, depart_date=ym, calendar_type="departure_date", currency="brl")),
                    "v2 prices/month-matrix": ("/v2/prices/month-matrix", dict(
                        origin=o, destination=d, month=f"{ym}-01", currency="brl", show_to_affiliates="false")),
                    "v2 prices/latest": ("/v2/prices/latest", dict(
                        origin=o, destination=d, beginning_of_period=f"{ym}-01", period_type="month",
                        one_way="true", limit=1000, currency="brl", show_to_affiliates="false")),
                }
                lines.append(f"== {o}→{d} {ym}")
                for name, (path, params) in variants.items():
                    try:
                        resp = get_json(BASE + path, params=params, headers=hdr, retries=1)
                        data = resp.get("data") if isinstance(resp, dict) else resp
                        n = _count(data)
                        sample = ""
                        if n:
                            first = data[0] if isinstance(data, list) else next(iter(data.values()))
                            sample = " ex.: " + str(first)[:160]
                        lines.append(f"   {n:4d}  {name}{sample}")
                    except Exception as e:  # queremos ver todos os erros
                        lines.append(f"   ERRO  {name}: {e}")
    return lines
