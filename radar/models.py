from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Offer:
    """Um trecho só de ida em um dia específico.

    Para ofertas em dinheiro, ``price`` é o preço da passagem e ``points`` é 0.
    Para resgates com pontos, ``points`` é o custo em pontos e ``price`` são as taxas.
    """

    origin: str
    destination: str
    day: date
    price: float
    points: int = 0
    airline: str = ""
    transfers: int | None = None
    link: str = ""
    provider: str = ""

    @property
    def is_award(self) -> bool:
        return self.points > 0


@dataclass(frozen=True)
class Trip:
    """Ida e volta combinando dois trechos."""

    out: Offer
    back: Offer
    extra_cost: float = 0.0

    @property
    def nights(self) -> int:
        return (self.back.day - self.out.day).days

    @property
    def total_price(self) -> float:
        return self.out.price + self.back.price + self.extra_cost

    @property
    def total_points(self) -> int:
        return self.out.points + self.back.points


@dataclass(frozen=True)
class Deal:
    """Oferta de ida e volta para um destino qualquer (vinda de cache de buscas)."""

    origin: str
    destination: str
    depart: date
    ret: date | None
    price: float
    airline: str = ""
    transfers: int | None = None
    link: str = ""
    provider: str = ""
    pax: int = 1  # ``price`` é o total para este número de pessoas

    @property
    def per_person(self) -> float:
        return self.price / max(1, self.pax)

    @property
    def nights(self) -> int | None:
        return (self.ret - self.depart).days if self.ret else None


@dataclass(frozen=True)
class Promo:
    title: str
    link: str
    published: date | None
    source: str
    kind: str                      # "transferencia", "passagem", "outro"
    bonus_pct: int | None = None   # maior % de bônus citado no título
    programs: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""
