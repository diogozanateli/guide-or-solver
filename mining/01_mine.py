"""Minera issues fechadas por PR mesclado no período configurado, nos
repositórios selecionados por 00_select_repos.py (data/repos.csv).

Saída: data/candidates.jsonl
Requer a variável de ambiente GITHUB_TOKEN.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.github import API, S, get  # noqa: E402
from common.utils import DATA, append_jsonl, load_config, read_jsonl, split_patch, patch_files  # noqa: E402

FIX_RE = re.compile(r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.I)


def selected_repos() -> list[str]:
    path = DATA / "repos.csv"
    if not path.exists():
        sys.exit("data/repos.csv não encontrado: rode mining/00_select_repos.py antes.")
    return [r["repo"] for r in csv.DictReader(path.open()) if r["status"] == "selected"]


def merged_prs(repo: str, since: str, until: str):
    q = f"repo:{repo} is:pr is:merged merged:{since}..{until}"
    page = 1
    while True:
        r = get(f"{API}/search/issues", q=q, per_page=100, page=page)
        r.raise_for_status()
        items = r.json()["items"]
        yield from items
        if len(items) < 100 or page >= 10:
            return
        page += 1


def main() -> None:
    cfg = load_config()["mining"]
    out = DATA / "candidates.jsonl"
    seen = {c["instance_id"] for c in read_jsonl(out)}
    for repo in selected_repos():
        count = 0
        for item in merged_prs(repo, cfg["since"], cfg["until"]):
            if count >= cfg["max_candidates_per_repo"]:
                break
            pr = get(item["pull_request"]["url"]).json()
            refs = FIX_RE.findall(pr.get("body") or "") + FIX_RE.findall(pr["title"])
            if not refs:
                continue
            issue_no = int(refs[0])
            iid = f"{repo.replace('/', '__')}-{issue_no}"
            if iid in seen:
                continue
            issue = get(f"{API}/repos/{repo}/issues/{issue_no}").json()
            if "pull_request" in issue or "title" not in issue or not (issue.get("body") or "").strip():
                continue
            diff = S.get(pr["url"], headers={"Accept": "application/vnd.github.v3.diff"}).text
            code_patch, test_patch = split_patch(diff)
            code_files = [f for f in patch_files(code_patch) if f.endswith(".py")]
            if not code_files or not test_patch or len(patch_files(code_patch)) > cfg["max_code_files"]:
                continue
            append_jsonl(out, {
                "instance_id": iid,
                "repo": repo,
                "issue_number": issue_no,
                "issue_title": issue["title"],
                "issue_body": issue["body"],
                "pr_number": pr["number"],
                "base_commit": None,  # resolvido em 02_validate.py (pai do merge commit)
                "merge_commit": pr["merge_commit_sha"],
                "code_patch": code_patch,
                "test_patch": test_patch,
                "created_at": issue["created_at"],
            })
            seen.add(iid)
            count += 1
            print(f"[+] {iid}")


if __name__ == "__main__":
    main()
