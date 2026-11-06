# Quitar los workflows que usan tokens de Claude

## 2026-11-06 — Éxito ✅

- **Rama:** `chore/quitar-workflows-claude`
- **PR:** la de esta rama → `develop` (sin issue: petición directa del mantenedor)
- **Origen:** el check «Claude · revisar PR» fallaba en todas las PRs porque el
  secreto `CLAUDE_CODE_OAUTH_TOKEN` ya no autentica. El mantenedor no quiere vincular
  el repositorio con ningún token de Claude Code.

### Qué se hizo y dónde

- Borrados `.github/workflows/claude-code-review.yml` (review automática de cada PR)
  y `.github/workflows/claude-daily-digest.yml` (digest diario): eran los dos únicos
  workflows que leían `CLAUDE_CODE_OAUTH_TOKEN` / `ANTHROPIC_API_KEY`.
- `CLAUDE.md` y `docs/governance/branch-protection.md`: ya no citan la review de
  Claude como parte de la revisión efectiva.

### Qué NO se hizo

- El secreto `CLAUDE_CODE_OAUTH_TOKEN` sigue en *Settings → Secrets* del repo; sin
  workflows que lo lean no se usa. Borrarlo es un paso aparte del mantenedor.
- El check no estaba entre los obligatorios del ruleset (`.github/rulesets/develop.json`),
  así que no hay que tocar la protección de rama.
