from __future__ import annotations

import time

import requests

USER_AGENT = "radar-passagens/0.1 (+uso pessoal)"


def get_json(url: str, *, params=None, headers=None, retries: int = 3, timeout: int = 30):
    """GET com algumas tentativas em caso de erro de rede ou 429/5xx."""
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=hdrs, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            last = e
            resp = getattr(e, "response", None)
            if resp is not None and 400 <= resp.status_code < 500 and resp.status_code != 429:
                raise
            time.sleep(2 ** attempt)
    assert last is not None
    raise last


def get_text(url: str, *, timeout: int = 30) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    return r.text
