# Guardrails (hooks de Claude Code)

Guardarraíles que se ejecutan **dentro de las sesiones de Claude Code**, *antes*
de que una herramienta actúe. Complementan a la CI y la branch protection (el
gate duro para todos): esto detiene acciones contra la gobernanza de forma
temprana, durante el trabajo asistido.

> Ámbito: solo aplican a sesiones de Claude Code en este repo (vía
> `.claude/settings.json`). No sustituyen a la CI ni a la protección de ramas.

## `guard_git.py` — política de ramas (GOVERNANCE §3)

Hook `PreToolUse` sobre `Bash`. Bloquea (`permissionDecision: deny`):

- `git commit` o `git push` cuando la rama actual es **protegida**
  (`develop`/`main`/`master`). El trabajo va en ramas `feat|fix|sec|docs|chore/…`.
- `git push --force`/`-f` hacia una rama protegida.

**Qué rama se evalúa.** La del directorio **al que apunta cada `git commit`/`git push`**:
`git -C <dir> …` o el último `cd <dir>` previo en el mismo comando; no solo la del
directorio de la sesión. Con *git worktrees* la sesión puede estar en `develop` mientras el
comando opera en un worktree con rama `feat/…` (se permite), o al revés: sesión en una rama
con prefijo y `cd` al repo que está en `develop` (se deniega). Si el comando toca varios
directorios, basta con que **uno** esté en una rama protegida para denegar. Ante cualquier
duda sobre el destino (ruta que no existe, `--git-dir`/`--work-tree`, comillas mal
cerradas) se evalúa la rama de la sesión, como antes. Límite conocido: no se interpretan
construcciones como `bash -c "cd x && git commit"` ni variables de shell en la ruta; en
esos casos manda la rama de la sesión. Tests: `backend/tests/test_guard_git_hook.py`.

Es **fail-open**: ante cualquier error o duda permite, para no estorbar (la CI +
branch protection son el control duro).

### Cómo probarlo

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git commit -m x"}}' \
  | python "$CLAUDE_PROJECT_DIR/.claude/hooks/guard_git.py"
# En develop → imprime una decisión "deny"; en una rama feature → sin salida (allow).
```

## Nota cross-platform

El comando configurado en `settings.json` es
`python "$CLAUDE_PROJECT_DIR/.claude/hooks/guard_git.py"` (ruta absoluta vía
`$CLAUDE_PROJECT_DIR` para que resuelva desde la raíz sin importar el cwd).
En entornos donde el intérprete sea `python3` (p. ej. macOS sin alias `python`),
ajusta el comando del hook a `python3` en tu `.claude/settings.local.json`
(que tiene prioridad y no se versiona).
