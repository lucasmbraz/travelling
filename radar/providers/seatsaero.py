"""Resgates com pontos Azul Fidelidade via Seats.aero (Partner API).

Requer assinatura Seats.aero Pro (≈ US$ 10/mês); a chave fica em
https://seats.aero/settings → API. Os dados são um cache atualizado várias vezes
por dia, cobrindo os próximos meses.
"""
from __future__ import annotations

from datetime import date

from radar.models import Offer
from radar.providers.http import get_json

BASE = "https://seats.aero/partnerapi"
SOURCE = "azul"


def _int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def parse_availability(row: dict, cabin: str = "Y") -> Offer | None:
    """Converte um item de disponibilidade em Offer (ou None se não houver assento)."""
    if not row.get(f"{cabin}Available"):
        return None
    points = _int(row.get(f"{cabin}MileageCost"))
    if points <= 0:
        return None
    route = row.get("Route") or {}
    taxes = row.get(f"{cabin}TotalTaxes")
    # Seats.aero informa taxas em centavos da moeda em TaxesCurrency.
    taxes_brl = _int(taxes) / 100 if taxes is not None and row.get("TaxesCurrency") in (None, "", "BRL") else 0.0
    return Offer(
        origin=route.get("OriginAirport", ""),
        destination=route.get("DestinationAirport", ""),
        day=date.fromisoformat(str(row.get("Date"))[:10]),
        price=taxes_brl,
        points=points,
        airline=row.get(f"{cabin}Airlines", "") or "",
        transfers=0 if row.get(f"{cabin}Direct") else None,
        link="https://seats.aero/azul",
        provider="seats.aero",
    )


class SeatsAeroProvider:
    name = "seats.aero"

    def __init__(self, api_key: str, max_pages: int = 5):
        self.api_key = api_key
        self.max_pages = max_pages

    def _paged(self, path: str, params: dict) -> list[dict]:
        headers = {"Partner-Authorization": self.api_key}
        rows: list[dict] = []
        params = {**params, "take": 1000}
        for _ in range(self.max_pages):
            data = get_json(f"{BASE}{path}", params=params, headers=headers)
            batch = data.get("data") or []
            rows.extend(batch)
            if not data.get("hasMore") or not batch:
                break
            params["cursor"] = data.get("cursor")
            params["skip"] = len(rows)
        return rows

    def one_way(self, origin: str, destinations: list[str], start: date, end: date) -> list[Offer]:
        rows = self._paged("/search", {
            "origin_airport": origin,
            "destination_airport": ",".join(destinations),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "sources": SOURCE,
        })
        return [o for o in (parse_availability(r) for r in rows) if o]

    def anywhere(self, origin: str, start: date, end: date) -> list[Offer]:
        """Todos os resgates Azul saindo de ``origin`` (via disponibilidade em massa)."""
        rows = self._paged("/availability", {
            "source": SOURCE,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "origin_region": "South America",
        })
        rows = [r for r in rows if (r.get("Route") or {}).get("OriginAirport") == origin]
        return [o for o in (parse_availability(r) for r in rows) if o]
