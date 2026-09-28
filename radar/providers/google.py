"""Preços em dinheiro do Google Voos, via biblioteca ``flights`` (fli).

Usa o "gráfico de datas" do Google Voos: uma consulta devolve o menor preço de
cada dia em até 61 dias. Não precisa de chave. Não é uma API oficial, então pode
parar de funcionar se o Google mudar algo; nesse caso o radar segue com as outras
fontes e mostra o erro nos avisos.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from radar import links
from radar.models import Offer

MAX_DAYS_AHEAD = 300  # o Google não aceita buscas muito à frente


def _airport(code: str):
    from fli.models import Airport

    try:
        return Airport[code.upper()]
    except KeyError:
        raise ValueError(f"aeroporto {code} não reconhecido pelo Google Voos") from None


class GoogleFlightsProvider:
    name = "Google Voos"
    calendar = True  # tem o menor preço de cada dia (não só o que alguém buscou)

    def __init__(self, currency: str = "BRL", language: str = "pt-BR", country: str = "BR", search=None):
        self.currency = currency
        self.language = language
        self.country = country
        self._search = search  # injetável nos testes

    def _client(self):
        if self._search is None:
            from fli.search import SearchDates

            self._search = SearchDates()
        return self._search

    def one_way_range(self, origin: str, destination: str, start: date, end: date,
                      adults: int = 1, children: int = 0, airline: str | None = None) -> list[Offer]:
        """Menor preço de cada dia, já somado para todos os passageiros.

        ``airline`` (ex.: "AD") restringe a uma companhia.
        """
        from fli.models import Airline, DateSearchFilters, FlightSegment, PassengerInfo, TripType

        today = date.today()
        start = max(start, today + timedelta(days=1))
        end = min(end, today + timedelta(days=MAX_DAYS_AHEAD))
        if end < start:
            return []
        filters = DateSearchFilters(
            trip_type=TripType.ONE_WAY,
            passenger_info=PassengerInfo(adults=adults, children=children),
            airlines=[Airline[airline]] if airline else None,
            flight_segments=[FlightSegment(
                departure_airport=[[_airport(origin), 0]],
                arrival_airport=[[_airport(destination), 0]],
                travel_date=start.isoformat(),
            )],
            from_date=start.isoformat(),
            to_date=end.isoformat(),
        )
        results = self._client().search(filters, currency=self.currency, language=self.language,
                                        country=self.country) or []
        offers = []
        for r in results:
            if r.currency and r.currency.upper() != self.currency:
                continue  # evita misturar moedas se o Google ignorar o pedido
            d = r.date[0].date() if isinstance(r.date[0], datetime) else r.date[0]
            if r.price and start <= d <= end:
                offers.append(Offer(origin, destination, d, float(r.price), airline=airline or "",
                                    link=links.google_flights(origin, destination, d), provider=self.name))
        return offers


def diagnose(origin: str, destinations: list[str], today: date, months: int) -> list[str]:
    """Mostra quantos dias com preço o Google Voos devolve para cada trecho e tipo de busca."""
    import time

    prov = GoogleFlightsProvider()
    start, end = today + timedelta(days=1), today + timedelta(days=30 * months)
    variants = [
        ("1 adulto", dict()),
        ("2 adultos", dict(adults=2)),
        ("5 adultos", dict(adults=5)),
        ("2 adultos + 3 crianças", dict(adults=2, children=3)),
        ("1 adulto, só Azul", dict(airline="AD")),
    ]
    lines = [f"### Google Voos ({start:%d/%m/%Y} a {end:%d/%m/%Y})"]
    for dest in destinations:
        for o, d in ((origin, dest), (dest, origin)):
            lines.append(f"== {o}→{d}")
            for name, kw in variants:
                t0 = time.monotonic()
                try:
                    offers = prov.one_way_range(o, d, start, end, **kw)
                    cheapest = min(offers, key=lambda x: x.price) if offers else None
                    extra = f" — mais barato R$ {cheapest.price:.0f} em {cheapest.day:%d/%m}" if cheapest else ""
                    lines.append(f"   {len(offers):4d} dias  {name} ({time.monotonic() - t0:.1f}s){extra}")
                except Exception as e:  # queremos ver o erro
                    lines.append(f"   ERRO  {name} ({time.monotonic() - t0:.1f}s): {type(e).__name__}: {e}")
    return lines
