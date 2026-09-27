"""Promoções a partir de feeds RSS de blogs de milhas e passagens."""
from __future__ import annotations

import html
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime
from email.utils import parsedate_to_datetime

from radar.models import Promo
from radar.providers.http import get_text

# Programas que interessam (chave -> palavras que identificam no texto).
KNOWN_PROGRAMS = {
    "azul": ["azul fidelidade", "tudoazul", "azul"],
    "livelo": ["livelo"],
    "inter": ["inter loop", "banco inter", "inter"],
    "esfera": ["esfera"],
    "smiles": ["smiles"],
    "latam": ["latam pass"],
}

TRANSFER_WORDS = ("transfer", "bonus", "bônus", "bonificad")
FARE_WORDS = ("passagens", "passagem", "voos", "ida e volta", "promo", "tarifa", "milhas")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(_norm(word))}\b", text) is not None


def _from_azul(title_n: str) -> bool:
    """True quando o título fala de transferir pontos DA Azul para outro programa."""
    if re.search(r"\bpara (a |o )?(azul|tudoazul)\b", title_n):
        return False
    return re.search(r"\b(azul|tudoazul)( fidelidade)? para\b", title_n) is not None


def classify(title: str, summary: str = "") -> tuple[str, int | None, tuple[str, ...]]:
    """Classifica um post: tipo, maior % de bônus citado e programas mencionados."""
    text = _norm(f"{title} {summary}")
    title_n = _norm(title)
    programs = tuple(k for k, words in KNOWN_PROGRAMS.items() if any(_has_word(text, w) for w in words))
    if "azul" in programs and _from_azul(title_n):
        # Ex.: "bônus ao transferir pontos Azul para ALL Accor" tira pontos da Azul:
        # não conta como promoção da Azul.
        programs = tuple(p for p in programs if p != "azul")
    pcts = [int(p) for p in re.findall(r"(\d{2,3})\s*%\s*(?:de\s+)?(?:bonus|bonificac)", title_n)]
    bonus = max(pcts) if pcts else None
    if bonus is not None or ("transfer" in title_n and any(w in title_n for w in ("bonus", "ponto"))):
        kind = "transferencia"
    elif any(w in title_n for w in FARE_WORDS):
        kind = "passagem"
    else:
        kind = "outro"
    return kind, bonus, programs


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).date()
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def parse_feed(xml_text: str, source: str) -> list[Promo]:
    """Lê RSS 2.0 ou Atom sem dependências externas."""
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    atom = "{http://www.w3.org/2005/Atom}"
    items = root.findall(".//item") or root.findall(f".//{atom}entry")
    promos = []
    for it in items:
        title = _strip_tags(it.findtext("title") or it.findtext(f"{atom}title") or "")
        link = (it.findtext("link") or "").strip()
        if not link:
            el = it.find(f"{atom}link")
            link = el.get("href", "") if el is not None else ""
        summary = _strip_tags(it.findtext("description") or it.findtext(f"{atom}summary") or "")[:400]
        published = _parse_date(it.findtext("pubDate") or it.findtext(f"{atom}updated") or it.findtext(f"{atom}published"))
        kind, bonus, programs = classify(title, summary)
        promos.append(Promo(title=title, link=link, published=published, source=source,
                            kind=kind, bonus_pct=bonus, programs=programs, summary=summary))
    return promos


class PromoProvider:
    name = "rss"

    def __init__(self, feeds: list[str]):
        self.feeds = feeds

    def fetch(self) -> tuple[list[Promo], list[str]]:
        promos, errors = [], []
        for url in self.feeds:
            source = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
            try:
                promos.extend(parse_feed(get_text(url), source))
            except Exception as e:  # um feed fora do ar não derruba o resto
                errors.append(f"{source}: {e}")
        return promos, errors


def relevant(promos: list[Promo], interests: set[str], places: list[str], today: date, recent_days: int) -> list[Promo]:
    """Filtra o que importa: bônus de transferência para Azul/seus programas e
    promoções de passagem que mencionem seus lugares."""
    out, seen = [], set()
    places_n = [_norm(p) for p in places if p]
    for p in promos:
        if p.link in seen:
            continue
        if p.published and (today - p.published).days > recent_days:
            continue
        text = _norm(f"{p.title} {p.summary}")
        if p.kind == "transferencia" and ("azul" in p.programs or interests & set(p.programs)):
            out.append(p)
        elif p.kind == "passagem" and any(_has_word(text, pl) for pl in places_n):
            out.append(p)
        else:
            continue
        seen.add(p.link)
    out.sort(key=lambda p: (p.kind != "transferencia", -(p.published or date.min).toordinal()))
    return out


def active_bonus(promos: list[Promo], program_keywords: list[str]) -> Promo | None:
    """Maior bônus de transferência para a Azul citando o programa informado."""
    best = None
    for p in promos:
        if p.kind != "transferencia" or p.bonus_pct is None or "azul" not in p.programs:
            continue
        text = _norm(f"{p.title} {p.summary}")
        if not any(_has_word(text, k) for k in program_keywords):
            continue
        if best is None or p.bonus_pct > (best.bonus_pct or 0):
            best = p
    return best
