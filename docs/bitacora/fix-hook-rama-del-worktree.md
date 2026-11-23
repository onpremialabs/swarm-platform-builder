# Fix: el guardarraíl de git evalúa la rama del directorio de destino

## 2026-11-23 — Éxito ✅

- **Rama:** `fix/hook-rama-del-worktree`
- **PR:** la de esta rama → `develop` (sin issue: fallo de tooling descubierto trabajando con
  varios agentes en paralelo)
- **Cambia un archivo de gobernanza** (`.claude/hooks/guard_git.py`): requiere revisión humana.

### Qué pasaba

`guard_git.py` decidía con `git rev-parse --abbrev-ref HEAD` ejecutado **en el directorio de
la sesión**. Los agentes de desarrollo trabajan en *git worktrees* (`C:/Proyectos/spb-<N>`,
cada uno con su rama `feat/…`) mientras la sesión vive en el repo principal. Cuando el repo
principal estaba en `develop` (porque ahí corre el servidor de desarrollo), el hook denegaba
todo `git commit`/`git push` aunque el comando operara en un worktree con rama válida. Pasó
con #536, #538 y en varias ocasiones más: los agentes se paraban sin poder commitear y la
persona tenía que cambiar de rama el repo principal a mano.

El caso inverso era un falso negativo: con la sesión en una rama con prefijo, un
`cd <repo en develop> && git commit` no se detectaba.

### Qué se hizo y dónde

- `.claude/hooks/guard_git.py`: `_target_branches` parte el comando en segmentos (fuera de
  comillas), sigue los `cd` y los `git -C`, y evalúa la rama de cada `git commit`/`git push`
  en su directorio real (`git -C <dir> rev-parse`). Entiende rutas `/c/…` de Git Bash en
  Windows. Si **algún** destino está en una rama protegida, deniega.
- **Conservador:** ante cualquier duda (directorio inexistente, `--git-dir`/`--work-tree`,
  comillas mal cerradas, ningún commit/push localizable) añade la rama de la sesión, que es el
  comportamiento anterior. Nunca permite algo que antes se denegaba por no entender el
  comando, salvo el caso explícito del destino válido en rama con prefijo.
- `.claude/hooks/README.md`: documenta qué rama se evalúa y los límites.
- `backend/tests/test_guard_git_hook.py`: 11 tests que ejecutan el hook real por stdin contra
  repos y worktrees reales (sesión en `develop` con `cd`/`git -C` a un worktree; sesión en
  rama con prefijo que entra en `develop`; destinos mixtos; destino irresoluble; el texto de
  un mensaje con `&&`/`;` no se interpreta; `--force` y `--no-verify` siguen denegados).

### Verificación

- `python -m pytest tests/test_guard_git_hook.py`: 11 passed (Windows).

### Qué NO se hizo / límites

- **El arreglo no actúa hasta que se mergee y el repo principal tenga ese archivo**: el hook
  que se ejecuta es el del directorio de la sesión. Hasta entonces el repo principal debe
  estar en una rama con prefijo para que los agentes puedan commitear.
- No se interpretan `bash -c "cd x && git commit"`, variables de shell en la ruta ni alias.
  Ahí sigue mandando la rama de la sesión.
- `--git-dir`/`--work-tree` apuntando a otro repositorio no se resuelven (caen a la rama de la
  sesión): un hueco previo que este cambio no empeora ni cierra.
- No se ha probado en Linux/macOS (el CI de GitHub corre Ubuntu y ejecutará los tests ahí).
