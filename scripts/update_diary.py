"""Atualiza as partes numéricas do DIARIO_EXPERIMENTO.md a partir dos arquivos gerados.

Só reescreve o conteúdo entre os marcadores
    <!-- AUTO:<bloco> -->  ...  <!-- /AUTO:<bloco> -->
O texto escrito à mão fora dos marcadores nunca é alterado. Blocos cujos dados
ainda não existem mostram "ainda não executado".

Uso: python scripts/update_diary.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.utils import DATA, RESULTS, ROOT, load_config, model_slug, read_jsonl  # noqa: E402

DIARY = ROOT / "DIARIO_EXPERIMENTO.md"
PENDING = "_Ainda não executado._"


# ---------------------------------------------------------------- utilitários
def table(header: list[str], rows: list[list]) -> str:
    def fmt(v):
        if isinstance(v, float):
            if v.is_integer():
                return str(int(v))
            return f"{v:.3f}" if abs(v) < 10 else f"{v:.1f}"
        return "" if v is None else str(v)
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(fmt(v) for v in r) + " |" for r in rows]
    return "\n".join(lines)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def counts(values, order: list[str] | None = None) -> list[list]:
    c = Counter(values)
    keys = order + sorted(k for k in c if k not in order) if order else [k for k, _ in c.most_common()]
    return [[k, c.get(k, 0)] for k in keys]


def mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def changed_lines(diff: str) -> int:
    return sum(1 for l in diff.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---")))


def models() -> list[str]:
    return [m["name"] for m in load_config()["models"]]


def environment_models() -> dict[str, dict]:
    """Extrai dos blocos '== <modelo>' do results/environment.txt (setup.sh) os dados
    do `ollama show` e o ID do `ollama list`."""
    path = RESULTS / "environment.txt"
    if not path.exists():
        return {}
    text = path.read_text(errors="ignore")
    out: dict[str, dict] = {}
    for m in re.finditer(r"^== (\S+)\n(.*?)(?=^== |\Z)", text, re.S | re.M):
        model, body = m.group(1), m.group(2)
        get = lambda k: (re.search(rf"^\s*{k}\s+(.+?)\s*$", body, re.M) or [None, ""])[1]
        idm = re.search(rf"^{re.escape(model)}\s+(\w+)\s", text, re.M)
        out[model] = {"id": idm.group(1) if idm else "", "architecture": get("architecture"),
                      "parameters": get("parameters"), "quantization": get("quantization"),
                      "context_length": get("context length")}
    return out


# ---------------------------------------------------------------- blocos
def block_modelos() -> str:
    path = RESULTS / "benchmarks.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    for model, info in environment_models().items():  # completa com o environment.txt
        data[model] = {**info, **data.get(model, {})}
    if not data:
        return PENDING + " (gerado a partir de `results/environment.txt` e `results/benchmarks.json`.)"
    keys = [("id", "ID Ollama"), ("architecture", "Arquitetura"), ("parameters", "Parâmetros"),
            ("quantization", "Quantização"), ("context_length", "Contexto máximo"),
            ("size_gb_gpu", "Memória na GPU (GB)"), ("processor", "Execução"),
            ("load_s", "Carga inicial (s)"), ("tokens_s", "Velocidade (tokens/s)"),
            ("measured_at", "Medido em")]
    names = list(data)
    rows = [[label] + [data[m].get(k, "") for m in names] for k, label in keys]
    return "Dados de `results/environment.txt` e medições da Etapa 1.1 (`results/benchmarks.json`):\n\n" + table(["Item"] + names, rows)


def block_selecao() -> str:
    repos = read_csv(DATA / "repos.csv")
    if not repos:
        return PENDING
    crit_path = DATA / "repos_criteria.json"
    queried = json.loads(crit_path.read_text())["queried_at"] if crit_path.exists() else repos[0]["queried_at"]
    sel = [r for r in repos if r["status"] == "selected"]
    order = ["C10_exclusao_manual", "C7_criado_recentemente", "C2_tamanho", "C3_nao_instalavel",
             "C8_poucos_testes", "C4_sem_pytest", "C5_extensao_compilada",
             "C9_dependencia_pesada", "C6_poucos_prs_vinculados"]
    excl = [r["reason"] for r in repos if r["status"] == "excluded"]
    out = [f"- Data da consulta: **{queried}**",
           f"- Repositórios avaliados (M): **{len(repos)}**",
           f"- Selecionados (N): **{len(sel)}**", "",
           table(["Critério de exclusão", "Repositórios"],
                 [r for r in counts(excl, order) if r[1]]), "",
           "Repositórios selecionados:", "",
           table(["Repositório", "Estrelas", "Criado em", "PRs vinculados no período"],
                 [[r["repo"], r["stars"], r.get("created_at", ""), r["linked_prs"]] for r in sel])]
    manual = [r for r in repos if r["reason"] == "C10_exclusao_manual"]
    if manual:
        out += ["", "Exclusões manuais (C10):", "",
                table(["Repositório", "Justificativa"], [[r["repo"], r.get("detail", "")] for r in manual])]
    return "\n".join(out)


def block_mineracao() -> str:
    log = read_csv(DATA / "mining_log.csv")
    cands = read_jsonl(DATA / "candidates.jsonl")
    if not log and not cands:
        return PENDING
    excl = [r["reason"].split(":")[0] for r in log if r["status"] == "excluded"]
    order = ["sem_vinculo_issue", "issue_duplicada", "issue_invalida_ou_sem_texto",
             "sem_codigo_python", "sem_testes", "patch_grande",
             "P1_autor_bot_ou_ia", "P1_commit_de_bot_ou_ia", "P2_marca_ia"]
    per_repo = Counter(c["repo"] for c in cands)
    selected = [r["repo"] for r in read_csv(DATA / "repos.csv") if r["status"] == "selected"]
    return "\n".join([
        f"- PRs avaliados: **{len(log)}**",
        f"- Candidatos: **{len(cands)}**", "",
        table(["Motivo de descarte", "PRs"], [r for r in counts(excl, order) if r[1]]), "",
        "Candidatos por repositório:", "",
        table(["Repositório", "Candidatos"], [[r, per_repo.get(r, 0)] for r in selected or per_repo]),
    ])


def block_validacao() -> str:
    ex = read_csv(DATA / "exclusions.csv")
    inst = read_jsonl(DATA / "instances.jsonl")
    if not ex and not inst:
        return PENDING
    order = ["historico_irrecuperavel", "checkout_falhou", "ambiente_nao_executavel",
             "test_patch_nao_aplica", "code_patch_nao_aplica", "testes_nao_executam",
             "testes_instaveis", "sem_fail_to_pass"]
    rows = counts([e["reason"] for e in ex], order)
    rows.append(["**Instâncias válidas (corpus final)**", f"**{len(inst)}**"])
    out = [table(["Motivo de exclusão", "Quantidade"], rows)]
    if inst:
        from common.utils import patch_files
        per_repo = Counter(i["repo"] for i in inst)
        out += ["", "Caracterização do corpus:", "", table(["Medida", "Valor"], [
            ["Projetos", len(per_repo)],
            ["Instâncias", len(inst)],
            ["Instâncias por projeto (mín–máx)", f"{min(per_repo.values())}–{max(per_repo.values())}"],
            ["Arquivos de código alterados no patch humano (média)",
             mean(len(patch_files(i["code_patch"])) for i in inst)],
            ["Linhas alteradas no patch humano (média)", mean(changed_lines(i["code_patch"]) for i in inst)],
            ["Testes FAIL_TO_PASS por instância (média)", mean(len(i["FAIL_TO_PASS"]) for i in inst)],
            ["Testes PASS_TO_PASS por instância (média)", mean(len(i["PASS_TO_PASS"]) for i in inst)],
        ]), "", table(["Repositório", "Instâncias"], [[r, n] for r, n in per_repo.most_common()])]
    return "\n".join(out)


def block_execucao() -> str:
    parts = []
    for name in models():
        d = RESULTS / model_slug(name)
        runs = sorted(d.glob("*/C*_run*.json")) if d.exists() else []
        if not runs:
            parts.append(f"**{name}:** {PENDING}")
            continue
        rows, statuses = [], Counter()
        by_cond: dict[str, list[dict]] = {}
        for f in runs:
            r = json.loads(f.read_text())
            by_cond.setdefault(f.stem.split("_")[0], []).append(r)
            statuses[(f.stem.split("_")[0], str(r.get("status")))] += 1
        for cond in sorted(by_cond):
            rs = by_cond[cond]
            rows.append([cond, len(rs), sum(1 for r in rs if not r.get("patch", "").strip()),
                         mean(r.get("actions") for r in rs), mean(r.get("duration_s") for r in rs)])
        cs = [json.loads(g.read_text()) for g in d.glob("*/codescout.json")]
        cs_rows = [
            ["Instâncias processadas", len(cs)],
            ["Alvos identificados (Stage 1, média)", mean(c["n_targets"] for c in cs)],
            ["Alvos recuperados e analisados (Stage 2, média)", mean(c["n_analyzed"] for c in cs)],
            ["Análises com relevância >= tau (média)", mean(c["n_kept"] for c in cs)],
            ["Instâncias sem nenhum alvo >= tau", sum(1 for c in cs if c["n_kept"] == 0)],
            ["Instâncias com 0 alvos parseados no Stage 1", sum(1 for c in cs if c["n_targets"] == 0)],
            ["Árvore de arquivos truncada", sum(1 for c in cs if c["file_tree_truncated"])],
            ["Chamadas ao LLM por instância (média)", mean(c["llm_calls"] for c in cs)],
            ["Tokens do CodeScout por instância (média)", mean(c["input_tokens"] + c["output_tokens"] for c in cs)],
            ["Duração do CodeScout por instância (s, média)", mean(c["duration_s"] for c in cs)],
            ["C2: 'Implementation Suggestions' encontrada e removida", sum(1 for c in cs if c["c2_removed_implementation"])],
            ["C2: código remanescente fora de Reproduction Steps", sum(1 for c in cs if c["c2_contains_code"])],
        ] if cs else []
        scores = [a["relevance"] for c in cs for a in c["analyses"]]
        valid = [x for x in scores if x is not None]
        tau = cs[0]["tau"] if cs else None
        score_rows = [[f"{b}", sum(1 for x in valid if int(x) == b)] for b in range(11)]
        score_rows.append(["sem nota (formato não seguido)", len(scores) - len(valid)])
        score_summary = (
            f"Distribuição das notas de relevância (Stage 2) — {len(scores)} análises; "
            f"média {mean(valid) or 0:.2f}; {sum(1 for x in valid if x >= tau)} com nota >= tau ({tau}):\n\n"
            + table(["Nota", "Análises"], score_rows)) if scores else ""
        n_inst = len({f.parent.name for f in runs})
        parts += [f"**{name}** — {n_inst} instâncias com execuções", "",
                  table(["Condição", "Execuções", "Patch vazio", "Ações (média)", "Duração (s, média)"], rows), "",
                  table(["Condição", "Status de encerramento", "Execuções"],
                        [[c, s, n] for (c, s), n in sorted(statuses.items())]), "",
                  ("CodeScout (contextualizador):\n\n" + table(["Medida", "Valor"], cs_rows))
                  if cs_rows else "CodeScout: _ainda não executado._", score_summary]
    return "\n\n".join(p for p in parts if p).strip()


def csv_table(path: Path, rename: dict[str, str] | None = None) -> str | None:
    rows = read_csv(path)
    if not rows:
        return None
    header = list(rows[0])
    conv = []
    for r in rows:
        line = []
        for h in header:
            v = r[h]
            try:
                v = float(v) if v not in ("", "True", "False") else v
            except ValueError:
                pass
            line.append(v)
        conv.append(line)
    return table([(rename or {}).get(h, h) for h in header], conv)


def block_resultados() -> str:
    parts = []
    for name in models():
        d = RESULTS / model_slug(name)
        sections = [("RQ1 — Resolução e eficiência", "rq1_summary.csv"),
                    ("RQ2 — Localização", "rq2_summary.csv"),
                    ("RQ3 — Relação com a correção humana", "rq3_summary.csv"),
                    ("Comparações pareadas (McNemar + Holm; IC 95% bootstrap)", "stats.csv")]
        body = [(t, csv_table(d / f)) for t, f in sections]
        if not any(b for _, b in body):
            parts.append(f"### {name}\n\n{PENDING}")
            continue
        parts.append(f"### {name}")
        for t, b in body:
            parts.append(f"**{t}**\n\n{b or PENDING}")
    return "\n\n".join(parts)


BLOCKS = {
    "modelos": block_modelos,
    "selecao": block_selecao,
    "mineracao": block_mineracao,
    "validacao": block_validacao,
    "execucao": block_execucao,
    "resultados": block_resultados,
}


def main() -> None:
    text = DIARY.read_text()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for name, fn in BLOCKS.items():
        pat = re.compile(rf"(<!-- AUTO:{name} -->\n).*?(\n<!-- /AUTO:{name} -->)", re.S)
        if not pat.search(text):
            print(f"[!] marcador AUTO:{name} não encontrado no diário — pulando")
            continue
        content = f"_Atualizado automaticamente em {stamp}._\n\n{fn()}"
        text = pat.sub(lambda m: m.group(1) + content + m.group(2), text)
        print(f"[ok] {name}")
    DIARY.write_text(text)


if __name__ == "__main__":
    main()
