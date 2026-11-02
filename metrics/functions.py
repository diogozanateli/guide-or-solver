"""Mapeia linhas alteradas de um diff para nomes qualificados de funções (Python)."""

from __future__ import annotations

import ast
import re

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def changed_lines(diff: str, side: str = "old") -> dict[str, set[int]]:
    """{arquivo: linhas alteradas} no lado 'old' (base) do diff."""
    files, cur, ln = {}, None, 0
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            cur = line.split(" b/")[-1].strip()
            files.setdefault(cur, set())
        elif m := HUNK.match(line):
            ln = int(m.group(1) if side == "old" else m.group(3))
        elif cur and line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            if (line[0] == "-") == (side == "old"):
                files[cur].add(ln)
                ln += 1
            else:
                files[cur].add(ln)  # inserção: atribui à linha vizinha
        elif cur and line.startswith(" "):
            ln += 1
    return files


def function_spans(source: str, module: str) -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}.{child.name}"
                if not isinstance(child, ast.ClassDef):
                    spans.append((name, child.lineno, child.end_lineno))
                visit(child, name)

    try:
        visit(ast.parse(source), module)
    except SyntaxError:
        pass
    return spans


def module_name(path: str) -> str:
    p = path[:-3] if path.endswith(".py") else path
    p = p.removeprefix("src/")
    return p.replace("/", ".").removesuffix(".__init__")


def changed_functions(diff: str, sources: dict[str, str], side: str = "old") -> set[str]:
    """sources: {arquivo: conteúdo do arquivo na revisão correspondente ao lado}."""
    result = set()
    for path, lines in changed_lines(diff, side).items():
        if not path.endswith(".py") or path not in sources:
            continue
        for name, start, end in function_spans(sources[path], module_name(path)):
            if any(start <= l <= end for l in lines):
                result.add(name)
    # remove funções externas quando uma interna também foi alterada
    return {f for f in result if not any(g.startswith(f + ".") for g in result)}
