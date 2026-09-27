"""Preços em dinheiro via Travelpayouts / Aviasales Data API.

Os dados vêm do cache de buscas feitas por usuários da Aviasales nos últimos dias,
então nem todo dia terá preço — mas é gratuito e aceita mês inteiro e destino em
aberto, que é justamente o que os sites das companhias não deixam fazer.

Token grátis: https://www.travelpayouts.com/ → Perfil → API token.
"""
from __future__ import annotations

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
    name = "travelpayouts"

    def __init__(self, token: str, market: str = "br", currency: str = "brl"):
        self.token = token
        self.market = market
        self.currency = currency

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
