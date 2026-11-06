# Desactivar Dependabot

## 2026-11-06 — Éxito ✅

- **Rama:** `chore/desactivar-dependabot`
- **PR:** la de esta rama → `develop` (sin issue: petición directa del mantenedor)
- **Origen:** Dependabot abría cada semana PRs de actualización (#489–#496) que nadie
  iba a revisar; el mantenedor pidió que dejara de hacerlo.

### Qué se hizo y dónde

- Borrado `.github/dependabot.yml`: sin ese fichero Dependabot deja de abrir PRs de
  versión. Las *security updates* automáticas ya estaban desactivadas en el repo.
- `backend/tests/test_supply_chain.py`: fuera los tres tests que exigían la
  configuración de Dependabot; los de `pip-audit`/`npm audit` y del lock se quedan.
- `docs/specs/SPEC-020-governance-supply-chain.md` (AC2) y `CLAUDE.md`: anotado que
  Dependabot está desactivado y que las dependencias se actualizan a mano.
- Cerradas sin mergear las PRs abiertas de Dependabot (#489, #490, #491, #492, #494,
  #495, #496).

### Qué NO se hizo

- El job `deps-audit` de la CI **sigue activo**: las vulnerabilidades conocidas
  siguen rompiendo la CI, aunque ya nadie proponga el parche automáticamente.

### Definition of Done

- [x] Dependabot sin configuración en el repo.
- [x] Tests de cadena de suministro en verde sin los de Dependabot.
- [x] Spec y CLAUDE.md actualizados.
