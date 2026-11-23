#!/usr/bin/env python3
"""Guardrail PreToolUse para comandos git (hook de Claude Code).

Aplica políticas de GOVERNANCE §3 y de higiene de seguridad *antes* de ejecutar:

- DENY: `git commit`/`git push` en rama protegida (develop/main/master).
- DENY: `git push --force`/`-f` hacia una rama protegida.
- DENY: `--no-verify` en commit/push (saltarse hooks/CI no está permitido).
- DENY: `git add -f`/`--force` de archivos sensibles ignorados
  (settings.local.json, .env, *.db, claves) — evita re-introducir secretos.
- ASK:  operaciones destructivas de historial/árbol (`git reset --hard`,
  `git clean -fd…`) — requieren confirmación explícita del usuario.

Entrada: JSON del hook por stdin (tool_name, tool_input.command).
Salida: JSON con permissionDecision (deny/ask). Si no aplica, sin salida (allow).
Fail-open: ante error o duda, permite (la CI + branch protection son el gate duro).

La rama que se evalúa es la del directorio **al que apunta cada `git commit`/`git push`**
(`git -C <dir>`, o el último `cd <dir>` previo en el mismo comando), no solo la del
directorio de la sesión: con git worktrees la sesión puede estar en `develop` mientras el
comando opera en un worktree con rama `feat/…`, y viceversa. Ante cualquier duda sobre el
destino se sigue evaluando la rama de la sesión (comportamiento anterior), y si **algún**
destino está en una rama protegida se deniega.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

PROTECTED = {"develop", "main", "master"}

# Archivos que nunca deben forzarse al índice (secretos / datos locales).
SENSITIVE = re.compile(
    r"(settings\.local\.json|\.env(\.[\w.-]+)?\b|\.db\b|\.pem\b|\.key\b|id_rsa)",
    re.IGNORECASE,
)


def _emit(decision: str, reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def _allow() -> None:
    sys.exit(0)


def _sanitize(cmd: str) -> str:
    """Quita cuerpos de heredoc y literales entrecomillados.

    Así los chequeos de flags no se disparan por el *contenido* de un mensaje de
    commit (p. ej. `-m "... --no-verify ..."`), solo por flags reales del comando.
    """
    cmd = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?[\s\S]*?\n\1\b", " ", cmd)  # heredocs
    cmd = re.sub(r"'[^']*'", " ", cmd)   # '...'
    cmd = re.sub(r'"[^"]*"', " ", cmd)   # "..."
    return cmd


def _branch_of(directory: str | None) -> str | None:
    """Rama actual del repositorio en `directory` (None = directorio de la sesión)."""
    cmd = ["git"] + (["-C", directory] if directory else []) + ["rev-parse", "--abbrev-ref", "HEAD"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def _current_branch() -> str | None:
    return _branch_of(None)


def _split_segments(raw: str) -> list[str]:
    """Parte el comando en segmentos por `&&`, `||`, `;`, `|` y saltos de línea fuera de comillas."""
    segmentos: list[str] = []
    actual: list[str] = []
    comilla = None
    i = 0
    while i < len(raw):
        c = raw[i]
        if comilla:
            actual.append(c)
            if c == comilla:
                comilla = None
        elif c in "'\"":
            comilla = c
            actual.append(c)
        elif c in ";\n" or c == "|" or (c == "&" and raw[i:i + 2] == "&&"):
            segmentos.append("".join(actual))
            actual = []
            if raw[i:i + 2] in ("&&", "||"):
                i += 1
        else:
            actual.append(c)
        i += 1
    segmentos.append("".join(actual))
    return [x.strip() for x in segmentos if x.strip()]


def _resolve_dir(base: str | None, path: str) -> str | None:
    """Resuelve `path` respecto de `base`; entiende `/c/…` de Git Bash en Windows."""
    if not path or path == "-":
        return None
    m = re.match(r"^/([a-zA-Z])/(.*)$", path)
    if os.name == "nt" and m:
        path = f"{m.group(1).upper()}:/{m.group(2)}"
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(base or os.getcwd(), path)
    return os.path.normpath(path)


def _target_branches(raw: str, session_cwd: str | None) -> set[str]:
    """Ramas de los directorios a los que apuntan los `git commit`/`git push` del comando.

    Conservador: si un segmento no se puede interpretar, o no hay ningún commit/push
    localizable, se añade la rama de la sesión (comportamiento anterior).
    """
    ramas: set[str] = set()
    sesion = _current_branch()
    dudoso = False
    directorio = session_cwd or None
    for segmento in _split_segments(raw):
        try:
            tokens = shlex.split(segmento, posix=True)
        except ValueError:
            if re.search(r"\bgit\b[^|&;]*\b(commit|push)\b", segmento):
                dudoso = True
            continue
        if not tokens:
            continue
        if tokens[0] == "cd":
            destino = _resolve_dir(directorio, tokens[1]) if len(tokens) > 1 else None
            if destino:
                directorio = destino
            else:
                dudoso = True  # `cd` sin destino claro: no se sabe dónde estamos
            continue
        if "git" not in tokens:
            continue
        i = tokens.index("git") + 1
        destino_git = directorio
        incierto = False
        while i < len(tokens) and tokens[i].startswith("-"):
            opcion = tokens[i]
            if opcion == "-C" and i + 1 < len(tokens):
                destino_git = _resolve_dir(destino_git, tokens[i + 1]) or destino_git
                i += 2
            elif opcion in ("-c", "--exec-path", "--namespace") and i + 1 < len(tokens):
                i += 2
            elif opcion.startswith(("--git-dir", "--work-tree")):
                incierto = True  # el repositorio real no es el del directorio
                i += 1
            else:
                i += 1
        subcomando = tokens[i] if i < len(tokens) else ""
        if subcomando not in ("commit", "push"):
            continue
        rama = None if incierto else _branch_of(destino_git)
        if rama is None:
            dudoso = True
        else:
            ramas.add(rama)
    if dudoso or not ramas:
        if sesion:
            ramas.add(sesion)
    return ramas


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        _allow()

    if data.get("tool_name") != "Bash":
        _allow()

    raw = (data.get("tool_input") or {}).get("command", "") or ""
    # Analizar sobre la versión saneada: ignora mensajes/heredocs entrecomillados.
    cmd = _sanitize(raw)
    if not re.search(r"\bgit\b", cmd):
        _allow()

    has_commit = bool(re.search(r"\bgit\b[^|&;]*\bcommit\b", cmd))
    has_push = bool(re.search(r"\bgit\b[^|&;]*\bpush\b", cmd))
    has_add = bool(re.search(r"\bgit\b[^|&;]*\badd\b", cmd))

    # 1) Saltarse las verificaciones (hooks/CI) no está permitido.
    if (has_commit or has_push) and re.search(r"\s--no-verify\b", cmd):
        _emit("deny",
              "No uses --no-verify: salta las verificaciones de commit/push. "
              "Corrige la causa en lugar de evitar el control.")

    # 2) Force-add de archivos sensibles ignorados.
    if has_add and re.search(r"\b(add)\b[^|&;]*\s(-f|--force)\b", cmd) and SENSITIVE.search(cmd):
        _emit("deny",
              "Bloqueado `git add --force` de un archivo sensible (secreto/datos "
              "locales). Esos archivos están ignorados a propósito; no los versiones.")

    branches = _target_branches(raw, data.get("cwd"))
    protegidas = sorted(b for b in branches if b in PROTECTED)
    branch = protegidas[0] if protegidas else (sorted(branches)[0] if branches else None)

    # 3) Force-push hacia rama protegida.
    if has_push and re.search(r"\s(--force(-with-lease)?|-f)\b", cmd):
        if branch in PROTECTED or re.search(r"\b(develop|main|master)\b", cmd):
            _emit("deny",
                  "Force-push hacia una rama protegida bloqueado (GOVERNANCE §3). "
                  "Si es imprescindible, hazlo tú manualmente fuera de la sesión.")

    # 4) Commit/push directo en rama protegida.
    if protegidas and (has_commit or has_push):
        action = "commitear" if has_commit else "hacer push"
        _emit("deny",
              f"No se permite {action} directamente en '{branch}' (GOVERNANCE §3). "
              f"Crea una rama `feat|fix|sec|docs|chore/…` y abre una PR a develop.")

    # 5) Operaciones destructivas → pedir confirmación.
    if re.search(r"\bgit\b[^|&;]*\breset\b[^|&;]*\s--hard\b", cmd):
        _emit("ask",
              "`git reset --hard` descarta cambios de forma irreversible. "
              "Confirma que es lo que quieres.")
    if re.search(r"\bgit\b[^|&;]*\bclean\b[^|&;]*\s-[a-z]*f[a-z]*d|\bgit\b[^|&;]*\bclean\b[^|&;]*\s-[a-z]*d[a-z]*f", cmd):
        _emit("ask",
              "`git clean -fd…` borra archivos no rastreados de forma irreversible. "
              "Confirma antes de continuar.")

    _allow()


if __name__ == "__main__":
    main()
