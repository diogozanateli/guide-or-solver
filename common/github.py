"""Cliente mínimo da API do GitHub com tratamento de limite de requisições."""

from __future__ import annotations

import os
import time

import requests

API = "https://api.github.com"
S = requests.Session()
S.headers.update({"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                  "Accept": "application/vnd.github+json"})


def get(url: str, headers: dict | None = None, **params) -> requests.Response:
    if not url.startswith("http"):
        url = API + url
    failures = 0
    while True:
        try:
            r = S.get(url, params=params, headers=headers, timeout=60)
        except (requests.ConnectionError, requests.Timeout) as e:
            # Quedas momentâneas de conexão: tenta de novo com espera crescente.
            failures += 1
            if failures > 8:
                raise
            wait = min(300, 5 * 2 ** (failures - 1))
            print(f"[rede] {type(e).__name__}; nova tentativa em {wait}s ({failures}/8)")
            time.sleep(wait)
            continue
        if r.status_code in (403, 429):
            if "Retry-After" in r.headers:
                time.sleep(int(r.headers["Retry-After"]) + 1)
                continue
            if r.headers.get("X-RateLimit-Remaining") == "0":
                time.sleep(max(1, int(r.headers["X-RateLimit-Reset"]) - int(time.time())) + 1)
                continue
        if r.status_code >= 500:
            time.sleep(5)
            continue
        return r


def search_count(q: str) -> int:
    """Número total de resultados de uma busca de issues/PRs (1 requisição)."""
    r = get("/search/issues", q=q, per_page=1)
    r.raise_for_status()
    time.sleep(2.1)  # limite da busca: 30 requisições/minuto
    return r.json()["total_count"]
