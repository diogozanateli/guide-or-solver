"""Reimplementação do CodeScout (Suri et al., 2026) a partir da Seção 4, do
Apêndice A (prompts) e do Algoritmo 1 do artigo. O código original não é público.

Pipeline (sem agente; apenas chamadas ao LLM):
  0. Estrutura do repositório: árvore de arquivos + índice AST (classes/funções)
  1. Stage 1 — Exploration Target Identification: 5–10 alvos (file/class/function)
  2. Stage 2 — Content Relevance Analysis: uma chamada por alvo recuperado,
     com nota RELEVANCE X/10 e quatro seções de análise
  3. Filtro de relevância: mantém análises com nota >= tau
  4. Stage 3 — Problem Statement Synthesis: especificação aumentada (C3)
  5. C2 = mesma especificação sem a subseção "Implementation Suggestions"
     (opção (a): C2 e C3 derivam da mesma análise)

Tudo (prompts, respostas, tokens, alvos, notas) é gravado em codescout.json.
"""

from __future__ import annotations

import ast
import re
import time
from pathlib import Path

import requests

from common.utils import ROOT, is_test_path, run
from metrics.functions import module_name

PROMPTS = ROOT / "prompts"
SECTIONS = ["ROLE_IN_ISSUE", "FIX_LOCATION_HINTS", "EXPLORATION_INSIGHTS", "ALTERNATIVE_HYPOTHESES"]


# ------------------------------------------------------------------ LLM
class LLM:
    """Chamadas diretas ao Ollama (/api/chat), registrando prompt, resposta e tokens."""

    def __init__(self, model_name: str, gen: dict):
        self.tag = model_name.split("/", 1)[-1]
        self.url = gen["api_base"].rstrip("/") + "/api/chat"
        self.options = {"temperature": gen["temperature"], "seed": gen["seed"],
                        "num_ctx": gen["num_ctx"]}
        self.calls: list[dict] = []

    def __call__(self, stage: str, prompt: str) -> str:
        t0 = time.time()
        last = None
        for attempt in range(3):  # erros transitórios de rede/servidor não devem perder o CodeScout inteiro
            try:
                r = requests.post(self.url, timeout=3600, json={
                    "model": self.tag, "stream": False, "options": self.options,
                    "messages": [{"role": "user", "content": prompt}]})
                r.raise_for_status()
                data = r.json()
                break
            except (requests.RequestException, ValueError) as e:
                last = e
                time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError(f"CodeScout: falha em {stage} após 3 tentativas: {last}")
        text = data["message"]["content"]
        pe = data.get("prompt_eval_count", 0) or 0
        self.calls.append({"stage": stage, "prompt": prompt, "response": text,
                           "input_tokens": pe,
                           "output_tokens": data.get("eval_count", 0) or 0,
                           # prompt do tamanho de num_ctx => o Ollama truncou o INÍCIO (instruções)
                           "done_reason": data.get("done_reason"),
                           "near_ctx_limit": pe >= 0.95 * self.options["num_ctx"],
                           "duration_s": round(time.time() - t0, 1)})
        return text


# ------------------------------------------------------------------ repositório
def tracked_files(repo: Path) -> list[str]:
    out = run("git ls-files", cwd=repo).stdout.splitlines()
    return sorted(f for f in out if f and not f.startswith(".venv/"))


def file_tree(files: list[str], max_chars: int) -> tuple[str, bool]:
    """Árvore de arquivos, um caminho por linha. Se exceder max_chars, remove primeiro
    arquivos que não são .py, depois testes/docs, e por fim trunca (registrado)."""
    tree = "\n".join(files)
    if len(tree) <= max_chars:
        return tree, False
    stages = [
        [f for f in files if f.endswith(".py")],
        [f for f in files if f.endswith(".py") and not is_test_path(f)
         and not f.startswith(("docs/", "doc/", "examples/"))],
    ]
    for subset in stages:
        tree = "\n".join(subset)
        if len(tree) <= max_chars:
            return tree + "\n(non-essential files omitted for length)", True
    return tree[:max_chars].rsplit("\n", 1)[0] + "\n(tree truncated for length)", True


class CodeIndex:
    """Índice AST de classes e funções (nomes qualificados e simples)."""

    def __init__(self, repo: Path, files: list[str]):
        self.repo, self.files = repo, files
        self.entities: list[dict] = []  # {type, qualname, name, path, start, end}
        for f in files:
            p = repo / f
            if not f.endswith(".py") or not p.is_file() or p.stat().st_size > 1_000_000:
                continue
            try:
                tree = ast.parse(p.read_text(errors="ignore"))
            except SyntaxError:
                continue
            self._visit(tree, module_name(f), f)

    def _visit(self, node, prefix: str, path: str, in_class: str | None = None):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}.{ch.name}"
                kind = "class" if isinstance(ch, ast.ClassDef) else "function"
                short = f"{in_class}.{ch.name}" if in_class else ch.name
                self.entities.append({"type": kind, "qualname": qual, "short": short,
                                      "name": ch.name, "path": path,
                                      "start": ch.lineno, "end": ch.end_lineno})
                self._visit(ch, qual, path, ch.name if kind == "class" else in_class)

    def find_file(self, name: str) -> str | None:
        name = name.strip().lstrip("./")
        if name in self.files:
            return name
        hits = [f for f in self.files if f.endswith("/" + name) or f == name]
        return hits[0] if hits else None

    def find_entity(self, name: str, kind: str | None) -> dict | None:
        name = re.sub(r"\(.*\)$", "", name.strip()).replace("::", ".")
        tests = lambda e: is_test_path(e["path"])  # prefere código-fonte a testes
        for match in (lambda e: e["qualname"] == name,
                      lambda e: e["qualname"].endswith("." + name),
                      lambda e: e["short"] == name,
                      lambda e: e["name"] == name.rsplit(".", 1)[-1]):
            hits = [e for e in self.entities if match(e) and (kind is None or e["type"] == kind)]
            if hits:
                return sorted(hits, key=tests)[0]
        return None

    def retrieve(self, target: dict, max_chars: int) -> tuple[str, dict] | None:
        ttype, name = target["target_type"], target["target_name"]
        path = self.find_file(name) if ttype == "file" or name.endswith(".py") else None
        if path:
            text = (self.repo / path).read_text(errors="ignore")
            return _clip(f"# File: {path}\n{text}", max_chars), {"path": path}
        ent = self.find_entity(name, ttype if ttype in ("class", "function") else None) \
            or self.find_entity(name, None)
        if ent:
            lines = (self.repo / ent["path"]).read_text(errors="ignore").splitlines()
            body = "\n".join(lines[ent["start"] - 1:ent["end"]])
            head = f"# {ent['type'].title()}: {ent['qualname']} ({ent['path']}, lines {ent['start']}-{ent['end']})\n"
            return _clip(head + body, max_chars), {"path": ent["path"], "qualname": ent["qualname"]}
        return None


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "\n# ... (truncated for length)"


# ------------------------------------------------------------------ parsing
TARGET_RE = re.compile(
    r"target_type\W*:\W*(file|class|function)\W*,\W*target_name\W*:\s*[`*\"']*(.+?)[`*\"']*\s*,"
    r"\s*\W*reasoning\W*:\s*(.+)", re.I)


def parse_targets(text: str, max_targets: int) -> list[dict]:
    seen, out = set(), []
    for line in text.splitlines():
        m = TARGET_RE.search(line)
        if not m:
            continue
        t = {"target_type": m.group(1).lower(), "target_name": m.group(2).strip(),
             "reasoning": m.group(3).strip()}
        key = (t["target_type"], t["target_name"])
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out[:max_targets]


def parse_analysis(text: str) -> dict:
    m = re.search(r"RELEVANCE\W*:?\s*(\d+(?:\.\d+)?)\s*/\s*10", text, re.I)
    score = float(m.group(1)) if m else None
    parts = re.split(r"\**\s*(" + "|".join(SECTIONS) + r")\s*\**\s*:\s*\**", text)
    sections = {k: "" for k in SECTIONS}
    for i in range(1, len(parts) - 1, 2):
        sections[parts[i].upper()] = parts[i + 1].strip().strip("*").strip()
    return {"relevance": score, **{k.lower(): v for k, v in sections.items()}}


def format_analyses(analyses: list[dict]) -> str:
    if not analyses:
        return "(no code analysis passed the relevance threshold)"
    blocks = []
    for i, a in enumerate(analyses, 1):
        rel = a["relevance"]
        rel = int(rel) if rel is not None and float(rel).is_integer() else rel
        blocks.append(
            f"{i}. TARGET: {a['target']['target_type']} - {a['target']['target_name']}\n"
            f"RELEVANCE: {rel}/10\n"
            f"ROLE IN ISSUE: {a['role_in_issue']}\n"
            f"FIX LOCATION HINTS: {a['fix_location_hints']}\n"
            f"EXPLORATION INSIGHTS: {a['exploration_insights']}\n"
            f"ALTERNATIVE HYPOTHESES: {a['alternative_hypotheses']}")
    return "\n\n".join(blocks)


# ------------------------------------------------------------------ C2 / localização
IMPL_RE = re.compile(r"^\s*(?:[-*•+]|\d+[.)]|#{2,6})?\s*\**\s*Implementation Suggestions", re.I)
SIBLING_RE = re.compile(
    r"^\s*(?:[-*•+]|\d+[.)]|#{2,6})?\s*\**\s*(High Confidence Locations|Alternative Hypothes[ie]s|"
    r"Files to Examine|Key Classes|Areas of Interest)", re.I)
HEADING_RE = re.compile(r"^\s*#{1,6}\s")


def remove_implementation(text: str) -> tuple[str, str]:
    """Remove a subseção "Implementation Suggestions" (item, parágrafos, sub-itens e
    blocos de código) até o próximo item irmão ou o próximo cabeçalho."""
    lines = text.splitlines()
    out, removed, skipping, in_fence = [], [], False, False
    for line in lines:
        if not skipping and IMPL_RE.match(line):
            skipping = True
            removed.append(line)
            continue
        if skipping:
            if line.strip().startswith("```"):
                in_fence = not in_fence
            elif not in_fence and (SIBLING_RE.match(line) or HEADING_RE.match(line)):
                skipping = False
            if skipping:
                removed.append(line)
                continue
        out.append(line)
    return "\n".join(out).strip() + "\n", "\n".join(removed).strip()


def section(text: str, title: str) -> str:
    m = re.search(rf"^#+\s*{title}.*?$(.*?)(?=^#+\s|\Z)", text, re.S | re.M | re.I)
    return m.group(1) if m else ""


def code_outside_reproduction(text: str, issue: str) -> list[str]:
    """Blocos de código fora de 'Reproduction Steps' que não vêm da issue original."""
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    issue_n = norm(issue)
    found = []
    for m in re.finditer(r"^#+\s*(.+?)$(.*?)(?=^#+\s|\Z)", text, re.S | re.M):
        if "reproduction" in m.group(1).lower():
            continue
        for block in re.findall(r"```[^\n]*\n(.*?)```", m.group(2), re.S):
            if norm(block) and norm(block) not in issue_n:
                found.append(block.strip()[:500])
    return found


# Nomes qualificados (Classe.metodo, modulo.funcao) ou nomes seguidos de "(".
FUNC_RE = re.compile(r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+|[A-Za-z_]\w*(?=\())")
NOT_FUNC = {"py", "md", "txt", "toml", "cfg", "ini", "yaml", "yml", "json", "rst", "html"}
PROSE = {"e.g", "i.e", "etc", "vs"}
# Primeiro segmento de nomes que não pertencem ao projeto (builtins e stdlib comuns).
BUILTIN_ROOTS = {"str", "list", "dict", "set", "tuple", "int", "float", "bool", "bytes",
                 "object", "type", "os", "sys", "re", "json", "typing", "collections",
                 "functools", "itertools", "pathlib", "logging", "np", "numpy", "pd"}
BUILTIN_FUNCS = {"print", "len", "isinstance", "getattr", "setattr", "hasattr", "open",
                 "range", "super", "repr", "format", "sorted", "map", "filter", "zip"}


def localization(text: str) -> dict:
    """Arquivos e funções indicados nas seções Exploration Hints e Fix Hints
    (High Confidence Locations) — usado na RQ2."""
    hints = section(text, "Exploration Hints")
    fix = section(text, "Fix Hints")
    hc = re.split(r"(?im)^\s*(?:[-*•+]|\d+[.)])?\s*\**\s*(?:Implementation Suggestions|Alternative Hypothes)", fix)[0]
    scope = hints + "\n" + hc
    files = sorted(set(re.findall(r"[\w./-]+\.py\b", scope)))
    funcs = set()
    for name in FUNC_RE.findall(scope):
        if name.rsplit(".", 1)[-1].lower() in NOT_FUNC or name.lower() in PROSE:
            continue
        if any(name in f for f in files):  # pedaço de caminho de arquivo
            continue
        name = name.removeprefix("self.").removeprefix("cls.")
        if name.split(".")[0] in BUILTIN_ROOTS or name in BUILTIN_FUNCS:
            continue
        funcs.add(name)
    return {"files": [f.lstrip("./") for f in files], "functions": sorted(funcs)}


# ------------------------------------------------------------------ pipeline
def run_codescout(repo: Path, problem_statement: str, model_name: str, gen: dict, cs: dict) -> dict:
    llm = LLM(model_name, gen)
    t0 = time.time()
    files = tracked_files(repo)
    tree, truncated = file_tree(files, cs["max_tree_chars"])
    index = CodeIndex(repo, files)

    # Stage 1 — Exploration Target Identification
    p1 = (PROMPTS / "codescout_stage1_scoping.md").read_text() \
        .replace("{problem_statement}", problem_statement).replace("{file_tree}", tree)
    targets = parse_targets(llm("stage1_scoping", p1), cs["max_targets"])

    # Stage 2 — Content Retrieval and Analysis
    p2_tpl = (PROMPTS / "codescout_stage2_analysis.md").read_text()
    analyses, unresolved = [], []
    for t in targets:
        got = index.retrieve(t, cs["max_target_chars"])
        if not got:  # o artigo ignora alvos não recuperados em vez de interromper
            unresolved.append(t)
            continue
        content, resolved = got
        p2 = (p2_tpl.replace("{problem_statement}", problem_statement)
              .replace("{content}", content)
              .replace("{target_type}", t["target_type"]).replace("{target_name}", t["target_name"]))
        a = parse_analysis(llm("stage2_analysis", p2))
        analyses.append({"target": t, "resolved": resolved, **a})

    # Stage 3 — Relevance Filtering (relevância >= tau)
    kept = [a for a in analyses if a["relevance"] is not None and a["relevance"] >= cs["tau"]]

    # Stage 4 — Synthesis
    p3 = (PROMPTS / "codescout_stage3_synthesis.md").read_text() \
        .replace("{original_ps}", problem_statement).replace("{analyses}", format_analyses(kept))
    ps_c3 = llm("stage3_synthesis", p3).strip() + "\n"
    ps_c2, removed = remove_implementation(ps_c3)
    leftover = code_outside_reproduction(ps_c2, problem_statement)

    return {
        "tau": cs["tau"], "file_tree_chars": len(tree), "file_tree_truncated": truncated,
        "n_files": len(files), "n_entities": len(index.entities),
        "targets": targets, "unresolved_targets": unresolved,
        "analyses": analyses, "kept": [analyses.index(a) for a in kept],
        "n_targets": len(targets), "n_analyzed": len(analyses), "n_kept": len(kept),
        "ps_aug_c3": ps_c3, "ps_aug_c2": ps_c2,
        "c2_removed_implementation": bool(removed), "c2_removed_text": removed,
        "c2_contains_code": bool(leftover), "c2_code_blocks": leftover,
        "guidance": {"C2": localization(ps_c2), "C3": localization(ps_c3)},
        "calls": llm.calls, "llm_calls": len(llm.calls),
        "any_truncated": any(c["near_ctx_limit"] or c["done_reason"] == "length" for c in llm.calls),
        "input_tokens": sum(c["input_tokens"] for c in llm.calls),
        "output_tokens": sum(c["output_tokens"] for c in llm.calls),
        "duration_s": round(time.time() - t0, 1),
    }
