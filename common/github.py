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
    while True:
        r = S.get(url, params=params, headers=headers)
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
