from __future__ import annotations

import calendar
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml


@dataclass
class Program:
    key: str
    name: str
    ratio: float = 1.0
    bonus: float = 0.0
    keywords: list[str] = field(default_factory=list)


@dataclass
class Route:
    destination: str
    name: str
    extra_cost: float = 0.0
    note: str = ""
    target_price: float | None = None
    target_points: int | None = None


@dataclass
class Window:
    name: str
    start: date
    end: date
    min_stay: int
    max_stay: int


@dataclass
class Config:
    origin: str
    balances: dict[str, int]
    programs: dict[str, Program]
    point_value: float
    routes: list[Route]
    windows: list[Window]
    anywhere_months: int = 3
    anywhere_max_price: float | None = None
    anywhere_exclude: list[str] = field(default_factory=list)
    feeds: list[str] = field(default_factory=list)
    promo_recent_days: int = 10
    drop_pct: float = 10.0

    def months_ahead(self, today: date, n: int) -> list[tuple[int, int]]:
        out, y, m = [], today.year, today.month
        for _ in range(n):
            out.append((y, m))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return out

    def horizon(self, today: date) -> tuple[date, date]:
        """Intervalo de datas que cobre todas as janelas configuradas."""
        start = min([w.start for w in self.windows], default=today)
        end = max([w.end for w in self.windows], default=today + timedelta(days=90))
        return max(start, today + timedelta(days=1)), end


def _to_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def load_config(path: str | Path, today: date | None = None) -> Config:
    today = today or date.today()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}

    programs = {
        key: Program(
            key=key,
            name=p.get("nome", key),
            ratio=float(p.get("proporcao", 1.0)),
            bonus=float(p.get("bonus", 0)),
            keywords=[k.lower() for k in p.get("palavras", [key])],
        )
        for key, p in (raw.get("programas") or {}).items()
    }

    routes = [
        Route(
            destination=r["destino"].upper(),
            name=r.get("nome", r["destino"]),
            extra_cost=float(r.get("custo_extra_reais", 0)),
            note=r.get("observacao", ""),
            target_price=r.get("alvo_reais"),
            target_points=r.get("alvo_pontos"),
        )
        for r in raw.get("rotas") or []
    ]

    windows = []
    for w in raw.get("janelas") or []:
        if "meses_a_frente" in w:
            start = today + timedelta(days=1)
            end = _add_months(today, int(w["meses_a_frente"]))
        else:
            start, end = _to_date(w["inicio"]), _to_date(w["fim"])
        if end <= today:
            continue  # janela já passou
        windows.append(
            Window(
                name=w.get("nome", f"{start} a {end}"),
                start=max(start, today + timedelta(days=1)),
                end=end,
                min_stay=int(w.get("estadia_min", 3)),
                max_stay=int(w.get("estadia_max", 15)),
            )
        )

    balances = {k: int(v or 0) for k, v in (raw.get("saldos") or {}).items()}
    # Saldos também podem vir de um segredo (ex.: SALDOS="azul=12000,livelo=30000")
    # para não ficarem públicos no repositório.
    for item in filter(None, os.environ.get("SALDOS", "").split(",")):
        k, _, v = item.partition("=")
        balances[k.strip()] = int(v.strip() or 0)

    anywhere = raw.get("qualquer_destino") or {}
    promos = raw.get("promocoes") or {}
    alerts = raw.get("alertas") or {}
    return Config(
        origin=raw.get("origem", "BEL").upper(),
        balances=balances,
        programs=programs,
        point_value=float(raw.get("valor_milheiro_azul", 16.0)),
        routes=routes,
        windows=windows,
        anywhere_months=int(anywhere.get("meses_a_frente", 3)),
        anywhere_max_price=anywhere.get("preco_max_alerta"),
        anywhere_exclude=[c.upper() for c in anywhere.get("excluir", [])],
        feeds=list(promos.get("feeds", [])),
        promo_recent_days=int(promos.get("dias_recentes", 10)),
        drop_pct=float(alerts.get("queda_minima_pct", 10)),
    )
