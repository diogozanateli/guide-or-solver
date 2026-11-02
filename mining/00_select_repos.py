"""Seleciona repositórios de forma reprodutível a partir de critérios fixos.

Critérios (config/experiment.yaml → selection):
  C1  linguagem principal Python, >= min_stars estrelas, não fork, não arquivado
      (busca do GitHub ordenada por estrelas; a API retorna no máximo 1000)
  C2  tamanho do repositório <= max_size_mb
  C3  pacote instalável: pyproject.toml, setup.py ou setup.cfg na raiz
  C4  usa pytest (configuração ou dependência declarada, ou conftest.py)
  C5  sem extensões compiladas (.c, .cpp, .pyx, .rs, Cargo.toml, ext_modules)
  C6  >= min_linked_prs PRs mesclados no período vinculados a uma issue

Saída: data/repos.csv com TODOS os repositórios avaliados, critério de exclusão
e data da consulta; os aprovados (até max_repos) são usados por 01_mine.py.
"""

from __future__ import annotations

import base64
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.github import get, search_count  # noqa: E402
from common.utils import DATA, load_config  # noqa: E402

COMPILED_EXT = (".c", ".cc", ".cpp", ".cxx", ".pyx", ".pxd", ".rs")
PKG_FILES = ("pyproject.toml", "setup.py", "setup.cfg")
PYTEST_FILES = ("pytest.ini", "tox.ini", "conftest.py", "tests/conftest.py")


def search_repos(cfg: dict):
    q = (f"language:Python stars:>={cfg['min_stars']} fork:false archived:false "
         f"pushed:>={cfg['since']}")
    for page in range(1, 11):
        r = get("/search/repositories", q=q, sort="stars", order="desc",
                per_page=100, page=page)
        r.raise_for_status()
        items = r.json()["items"]
        yield from items
        if len(items) < 100:
            return


def file_text(repo: str, path: str) -> str:
    r = get(f"/repos/{repo}/contents/{path}")
    if r.status_code != 200 or isinstance(r.json(), list):
        return ""
    return base64.b64decode(r.json().get("content", "")).decode("utf-8", "ignore")


def evaluate(item: dict, cfg: dict) -> str | None:
    """Retorna o critério que excluiu o repositório, ou None se aprovado."""
    repo = item["full_name"]
    if item["size"] / 1024 > cfg["max_size_mb"]:
        return "C2_tamanho"
    tree = get(f"/repos/{repo}/git/trees/{item['default_branch']}", recursive=1).json()
    paths = [t["path"] for t in tree.get("tree", []) if t["type"] == "blob"]
    root = {p for p in paths if "/" not in p}
    if not root & set(PKG_FILES):
        return "C3_nao_instalavel"

    build_text = "".join(file_text(repo, f) for f in PKG_FILES if f in root)
    has_pytest = (any(p in paths for p in PYTEST_FILES)
                  or "pytest" in build_text
                  or any("pytest" in file_text(repo, p) for p in paths
                         if p.startswith("requirements") and p.endswith(".txt")))
    if not has_pytest:
        return "C4_sem_pytest"

    src = [p for p in paths if not p.startswith(("tests/", "test/", "docs/",
                                                 "benchmarks/", "examples/"))]
    if ("Cargo.toml" in paths or any(p.endswith(COMPILED_EXT) for p in src)
            or "ext_modules" in build_text or "Extension(" in build_text):
        return "C5_extensao_compilada"

    n = search_count(f"repo:{repo} is:pr is:merged linked:issue "
                     f"merged:{cfg['since']}..{cfg['until']}")
    item["_linked_prs"] = n
    if n < cfg["min_linked_prs"]:
        return "C6_poucos_prs_vinculados"
    return None


def main() -> None:
    cfg = load_config()
    sel = {**cfg["selection"], "since": cfg["mining"]["since"], "until": cfg["mining"]["until"]}
    queried_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = DATA / "repos.csv"
    approved = 0
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["repo", "stars", "size_mb", "linked_prs", "status", "reason", "queried_at"])
        for item in search_repos(sel):
            if approved >= sel["max_repos"]:
                break
            reason = evaluate(item, sel)
            status = "selected" if reason is None else "excluded"
            approved += reason is None
            w.writerow([item["full_name"], item["stargazers_count"],
                        round(item["size"] / 1024, 1), item.get("_linked_prs", ""),
                        status, reason or "", queried_at])
            f.flush()
            print(f"[{'+' if reason is None else '-'}] {item['full_name']} {reason or ''}")
    print(f"{approved} repositórios selecionados → {out}")


if __name__ == "__main__":
    main()
