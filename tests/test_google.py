from datetime import date, datetime, timedelta

import pytest

from radar.providers import google

pytest.importorskip("fli")


class FakeResult:
    def __init__(self, d, price, currency="BRL"):
        self.date = (datetime.combine(d, datetime.min.time()),)
        self.price = price
        self.currency = currency


class FakeSearch:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def search(self, filters, currency=None, language=None, country=None):
        self.calls.append((filters, currency, language, country))
        return self.results


def test_google_one_way_range_parses_prices():
    d1 = date.today() + timedelta(days=10)
    d2 = date.today() + timedelta(days=11)
    fake = FakeSearch([FakeResult(d1, 612.0), FakeResult(d2, 540.0), FakeResult(d2, 99.0, "USD")])
    prov = google.GoogleFlightsProvider(search=fake)
    offers = prov.one_way_range("BEL", "MCZ", date.today(), date.today() + timedelta(days=60))
    assert [(o.day, o.price) for o in offers] == [(d1, 612.0), (d2, 540.0)]
    assert offers[0].provider == "Google Voos" and "google.com/travel/flights" in offers[0].link
    filters, currency, language, country = fake.calls[0]
    assert (currency, language, country) == ("BRL", "pt-BR", "BR")
    assert filters.from_date == (date.today() + timedelta(days=1)).isoformat()  # nunca hoje/passado


def test_google_unknown_airport():
    with pytest.raises(ValueError, match="XYZ1"):
        google.GoogleFlightsProvider(search=FakeSearch([])).one_way_range(
            "BEL", "XYZ1", date.today(), date.today() + timedelta(days=5))
