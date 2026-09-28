from datetime import date

from radar.providers import seatsaero, travelpayouts


def test_travelpayouts_parses_both_endpoints(monkeypatch):
    calls = []

    def fake(url, params=None, headers=None):
        calls.append((url, params, headers))
        if url.endswith("prices_for_dates"):
            return {"success": True, "data": [
                {"origin_airport": "BEL", "destination_airport": "MCZ", "price": 612, "airline": "AD",
                 "departure_at": "2026-12-18T06:10:00-03:00", "transfers": 1, "link": "/search/BEL1812MCZ1"}]}
        return {"success": True, "data": {"2026-12-19": {"price": 540, "airline": "G3",
                                                         "departure_at": "2026-12-19T10:00:00-03:00"}}}

    monkeypatch.setattr(travelpayouts, "get_json", fake)
    offers = travelpayouts.TravelpayoutsProvider("tok").one_way_month("BEL", "MCZ", 2026, 12)
    assert {(o.day, o.price) for o in offers} == {(date(2026, 12, 18), 612), (date(2026, 12, 19), 540)}
    assert offers[0].link.startswith("https://www.aviasales.com/search/")
    assert calls[0][2] == {"X-Access-Token": "tok"} and calls[0][1]["departure_at"] == "2026-12"


def test_travelpayouts_anywhere(monkeypatch):
    monkeypatch.setattr(travelpayouts, "get_json", lambda *a, **k: {"success": True, "data": [
        {"origin_airport": "BEL", "destination_airport": "LIM", "price": 1500,
         "departure_at": "2026-10-10T01:00:00-03:00", "return_at": "2026-10-17T01:00:00-05:00"}]})
    [d] = travelpayouts.TravelpayoutsProvider("t").anywhere_month("BEL", 2026, 10)
    assert d.destination == "LIM" and d.nights == 7


def test_seats_aero_parses_and_paginates(monkeypatch):
    pages = [
        {"data": [{"Date": "2026-12-20", "Route": {"OriginAirport": "BEL", "DestinationAirport": "MCZ"},
                   "YAvailable": True, "YMileageCost": "18500", "YTotalTaxes": 3790, "TaxesCurrency": "BRL",
                   "YAirlines": "AD", "YDirect": False}], "hasMore": True, "cursor": 123},
        {"data": [{"Date": "2026-12-21", "Route": {"OriginAirport": "BEL", "DestinationAirport": "MCZ"},
                   "YAvailable": False, "YMileageCost": "0"}], "hasMore": False},
    ]
    seen = []

    def fake(url, params=None, headers=None):
        seen.append(dict(params))
        return pages[len(seen) - 1]

    monkeypatch.setattr(seatsaero, "get_json", fake)
    [o] = seatsaero.SeatsAeroProvider("k").one_way("BEL", ["MCZ"], date(2026, 12, 1), date(2026, 12, 31))
    assert o.points == 18500 and o.price == 37.9 and o.day == date(2026, 12, 20)
    assert seen[0]["sources"] == "azul" and seen[1]["cursor"] == 123


def test_diagnose_reports_counts_and_errors(monkeypatch):
    def fake(url, params=None, headers=None, retries=3):
        if "calendar" in url:
            raise RuntimeError("HTTP 400")
        if "grouped" in url:
            return {"success": True, "data": {"2026-10-01": {"price": 500}, "2026-10-02": {"price": 600}}}
        return {"success": True, "data": []}

    monkeypatch.setattr(travelpayouts, "get_json", fake)
    lines = travelpayouts.diagnose("t", "BEL", ["MCZ"], [(2026, 10)])
    assert lines[:2] == ["### Travelpayouts", "== BEL→MCZ 2026-10"]
    assert any(line.strip().startswith("2  v3 grouped_prices") for line in lines)
    assert any("ERRO  v1 prices/calendar" in line for line in lines)
    assert sum(line.startswith("==") for line in lines) == 2  # ida e volta


def test_travelpayouts_group_prices_are_multiplied_and_cached(monkeypatch):
    calls = []

    def fake(url, params=None, headers=None):
        calls.append(url)
        if url.endswith("prices_for_dates"):
            return {"success": True, "data": [
                {"price": 600, "airline": "AD", "departure_at": "2026-12-18T06:10:00-03:00"},
                {"price": 500, "airline": "G3", "departure_at": "2026-12-19T06:10:00-03:00"}]}
        return {"success": True, "data": {}}

    monkeypatch.setattr(travelpayouts, "get_json", fake)
    p = travelpayouts.TravelpayoutsProvider("t")
    fam = p.one_way_range("BEL", "MCZ", date(2026, 12, 1), date(2026, 12, 31), adults=2, children=3)
    assert sorted(o.price for o in fam) == [2500, 3000] and fam[0].provider == "Travelpayouts (×5 estimado)"
    n_calls = len(calls)
    azul = p.one_way_range("BEL", "MCZ", date(2026, 12, 1), date(2026, 12, 31), airline="AD")
    assert [o.price for o in azul] == [600] and len(calls) == n_calls  # usou o cache
