"""Links prontos para conferir/comprar a combinação encontrada."""
from __future__ import annotations

from datetime import date
from urllib.parse import quote, urlencode


def google_flights(origin: str, dest: str, out: date, back: date | None = None) -> str:
    q = f"Flights from {origin} to {dest} on {out.isoformat()}"
    if back:
        q += f" through {back.isoformat()}"
    return "https://www.google.com/travel/flights?hl=pt-BR&curr=BRL&q=" + quote(q)


def azul(origin: str, dest: str, out: date, back: date | None = None, points: bool = False) -> str:
    """Abre a busca da Azul já preenchida (cc=PTS mostra preço em pontos)."""
    params = {
        "c[0].ds": origin, "c[0].std": out.strftime("%m/%d/%Y"), "c[0].as": dest,
        "p[0].t": "ADT", "p[0].c": 1, "p[0].cp": "false",
        "f.dl": 3, "f.dr": 3, "cc": "PTS" if points else "BRL",
    }
    if back:
        params.update({"c[1].ds": dest, "c[1].std": back.strftime("%m/%d/%Y"), "c[1].as": origin})
    return "https://www.voeazul.com.br/br/pt/home/selecao-voo?" + urlencode(params)
