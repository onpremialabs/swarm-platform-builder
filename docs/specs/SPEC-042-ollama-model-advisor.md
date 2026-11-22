# SPEC-042: Recomendación de modelos Ollama por agente según VRAM y RAM disponibles

- **Estado:** Draft
- **Autor:** Equipo de plataforma (borrador asistido)
- **Fecha:** 2026-11-22
- **Épica:** E30 (GitHub Project)
- **ADR relacionado:** ninguno (si la recomendación pasa a aplicarse sola, hace falta un ADR)
- **Severidad:** 🟡 (mejora de uso en la ruta on-prem/Ollama)

> **Estado de autoría:** Draft. Clarificada el 2026-11-22 (5 preguntas, ver
> `## Clarifications`; sin `[NEEDS CLARIFICATION]` abiertos). Antes de pasar a Ready
> conviene `/speckit-analyze SPEC-042`.
> Complementa a [SPEC-023](SPEC-023-claude-default-engine.md) (E12, cascada de modelo por
> agente) y puede apoyarse en [SPEC-025](SPEC-025-model-benchmark-scientific-writing.md)
> (E13, benchmark). No sustituye a ninguna.

## Clarifications

### Session 2026-11-22

- Q: ¿Dónde se declara el perfil de rol de cada agente? → A: En el `.agent.md` de cada
  agente (`model_profile:`), validado al cargar el proyecto (opción A).
- Q: ¿Cómo sabe el backend que Ollama corre en su misma máquina? → A: Solo `localhost` y
  `127.0.0.1` se miden; en cualquier otro caso (incluido `host.docker.internal`) el hardware
  es `unavailable` o la capacidad declarada a mano. Sin variable de entorno que lo fuerce
  (opción B).
- Q: ¿Qué valores usa el estimador de encaje (`k` y margen por `num_ctx`)? → A: Constantes
  conservadoras documentadas, `k = 1.2` y un margen fijo por cada 1.000 tokens de `num_ctx`,
  a ajustar después con datos; no configurables por la persona (opción A).
- Q: ¿Qué rol tiene el publicador, que no llama al LLM? → A: `model_profile` es opcional; un
  agente sin perfil no recibe sugerencia y la pantalla lo indica como «no usa modelo»
  (opción A).
- Q: ¿A qué ámbito se aplica el modelo aceptado? → A: Por proyecto: se guarda en los ajustes
  del agente de ese proyecto y no afecta a los demás (opción A).

## 1. Problema

La plataforma ya sabe **qué modelos Ollama hay instalados** y **resolver el modelo de cada
agente**, pero no ayuda a **elegirlos**: la persona usuaria tiene que adivinar cuál cabe
en su máquina y cuál conviene a cada agente.

Evidencia:

- `backend/app/routers/agents.py:565` y `backend/app/routers/ai.py:52` listan los modelos
  con `/api/tags` y devuelven solo los **nombres**: no el tamaño, la cuantización ni si cabe.
- `backend/app/platform/llm.py:193` (`resolve_agent_model`) aplica la cascada ajustes de la
  ejecución → `.agent.md` → default del proveedor. Es el sitio donde una elección se
  aplicaría, pero nada la propone.
- La selección de `models.ollama` de los `.agent.md` se hizo a mano y es **provisional**
  (SPEC-025, T13.3 pendiente de ratificar).
- No existe detección de hardware: no hay lectura de VRAM ni RAM en el backend. Un modelo
  que no cabe en VRAM no falla de forma clara: Ollama lo descarga a CPU o lo trunca y la
  ejecución se vuelve lenta o aborta a mitad del pipeline.

Importa porque el pipeline corre agentes **en secuencia** y cada uno usa `keep_alive=0`,
así que los modelos **no coexisten en memoria**: el límite relevante es el del modelo más
grande de **un** agente, no la suma. Hoy esa holgura no se aprovecha.

## 2. Objetivos / No-objetivos

- **Objetivos:**
  - Mostrar los modelos Ollama instalados con su tamaño y si **caben** en la memoria
    disponible.
  - Detectar la VRAM y la RAM libres, y degradar a «sin datos» cuando no se pueden leer
    (incluido Ollama en otra máquina), con la posibilidad de declarar la capacidad a mano.
  - Sugerir, **por agente**, el mejor modelo instalado que quepa, **explicando por qué**.
  - Aplicar la sugerencia solo con **confirmación** de la persona, por la cascada de
    SPEC-023, y dejar el origen de la elección en la traza de explicabilidad.
- **No-objetivos:**
  - **No descargar modelos** (`ollama pull`) ni instalar nada: solo se eligen los ya instalados.
  - **No afirmar calidad medida.** La recomendación es una heurística de tamaño y rol; solo
    cita datos de SPEC-025 cuando existan y los marca como tales.
  - **No asignar automáticamente.** Una elección cambia el resultado científico y debe ser
    una decisión de la persona.
  - No tocar los proveedores Anthropic/OpenAI: aplica solo con `LLM_PROVIDER=ollama`.
  - No medir rendimiento real (tokens/s) en esta spec: eso es del harness de SPEC-025.

## 3. Criterios de aceptación (Given/When/Then)

- [ ] **AC1** — *Given* un Ollama accesible *When* se consulta el inventario *Then* cada
  modelo instalado aparece con su nombre, tamaño en disco, familia y cuantización cuando
  Ollama los informa, y sin esos campos si no los informa (nunca inventados).
- [ ] **AC2** — *Given* el backend con acceso al hardware *When* se consulta el hardware
  *Then* se devuelven VRAM total y libre, y RAM total y libre, con la fuente de cada dato
  (`detected`, `declared` o `unavailable`).
- [ ] **AC3** — *Given* que el hardware no se puede leer (Ollama remoto o sin GPU detectable)
  *When* se consulta el hardware *Then* el estado es `unavailable`, el inventario sigue
  funcionando y la recomendación se marca «sin datos de hardware» en lugar de calcularse.
- [ ] **AC4** — *Given* una capacidad declarada a mano (`OLLAMA_VRAM_GB`, `OLLAMA_RAM_GB`)
  *When* se consulta el hardware *Then* esa capacidad manda sobre la detectada y la fuente
  es `declared`; un valor no numérico o ≤ 0 se rechaza al cargar la configuración.
- [ ] **AC5** — *Given* un modelo y un hardware *When* se estima si cabe *Then* el resultado
  es `fits_gpu`, `fits_partial` (parte en CPU), `fits_cpu` o `does_not_fit`, calculado con
  el tamaño del modelo más un margen para el contexto (el `num_ctx` real con el que el agente
  llama al modelo), y el cálculo es
  determinista (mismas entradas, mismo resultado).
- [ ] **AC6** — *Given* el inventario y el hardware *When* se pide la recomendación *Then*
  cada agente del proyecto **con `model_profile`** recibe como máximo un modelo sugerido, que
  **cabe** (`fits_gpu`, o `fits_partial` solo si ningún otro cabe y se avisa), con un motivo legible; si ningún
  modelo cabe, el agente no recibe sugerencia y se dice por qué. Un agente sin `model_profile`
  (incluidos los creados desde la UI, que no tienen `.agent.md`) no recibe sugerencia.
- [ ] **AC7** — *Given* que los agentes se ejecutan en secuencia con `keep_alive=0` *When* se
  calcula la recomendación *Then* cada agente se evalúa contra la memoria **completa**, no
  contra la suma de los modelos de los demás agentes; un agente que no usa `keep_alive=0`
  (su modelo puede seguir cargado) lo indica en el motivo de su sugerencia.
- [ ] **AC8** — *Given* una sugerencia *When* la persona la acepta *Then* el modelo se guarda
  en el **perfil del agente del proyecto activo** (`AgentProfileModel.model`, sin afectar a
  otros proyectos) y `resolve_agent_model` lo devuelve; si no la acepta, nada cambia. Ninguna ejecución usa una sugerencia que no se haya aceptado.
- [ ] **AC9** — *Given* un agente con modelo elegido desde una sugerencia *When* se ejecuta
  *Then* la traza del paso (`agent_run_steps`) registra el modelo y, dentro de `params`, que su
  origen fue `recommendation_accepted`, y el panel «Por qué este resultado» lo muestra; el
  registro de auditoría guarda quién aceptó la sugerencia y cuándo.
- [ ] **AC10** — *Given* el proveedor activo distinto de Ollama *When* se consulta cualquiera
  de estos endpoints *Then* responden «no aplica al proveedor activo» y no llaman a Ollama.
- [ ] **AC11** — *Given* la pantalla de modelos *When* se abre *Then* muestra el hardware y su
  fuente, el inventario con el «cabe / no cabe» en texto (no solo color), la sugerencia por
  agente con su motivo y un botón para aceptarla; con estados de carga, error con reintento
  y vacío (sin modelos instalados), y es operable con teclado.
- [ ] **AC12** — *Given* la recomendación *When* se muestra *Then* se rotula como
  **sugerencia por tamaño y rol, no por calidad medida**, y cuando SPEC-025 publique
  puntuaciones por modelo y rol las muestra con su procedencia; hasta entonces solo aplica el
  rótulo.

## 4. Diseño propuesto

**Dónde vive.** `backend/app/platform/model_advisor/` (nuevo), dentro de la capa
`platform/`: no menciona ningún agente del proyecto. El proyecto aporta el **rol** de cada
agente por registro, no por importación.

**Inventario (AC1, AC10).** `inventory.py` llama a Ollama `/api/tags` y conserva `size`,
`details.family`, `details.parameter_size` y `details.quantization_level`. La URL sale de
`OLLAMA_BASE_URL` (configuración, no entrada de usuario), así que queda fuera de `egress.py`
igual que el resto de llamadas a Ollama (CLAUDE.md, «Egress»). Con otro proveedor activo
responde `applicable: false`.

**Hardware (AC2–AC4).** `hardware.py` devuelve un `HardwareReport` con campos opcionales y
la fuente de cada uno:
1. Si hay `OLLAMA_VRAM_GB` / `OLLAMA_RAM_GB` en la configuración (precedencia habitual:
   entorno, luego `config.yaml`, luego los valores por defecto de `config.py`), manda lo
   declarado.
2. Si no, y Ollama corre en la misma máquina que el backend, lee la VRAM con la utilidad de
   la GPU y la RAM con el sistema operativo; cada lectura es opcional y falla a
   `unavailable`.
3. `/api/ps` informa qué hay cargado y cuánto está en VRAM (`size_vram`): sirve para
   **comprobar** el cálculo, no para conocer la capacidad total.

La detección de «Ollama en la misma máquina» se decide **solo** por la URL: `localhost` y
`127.0.0.1`. En cualquier otro caso (incluido `host.docker.internal`, porque el backend dentro
del contenedor no ve la GPU del anfitrión) no se mide el hardware del backend, porque sería el
equivocado: el estado es `unavailable` o la capacidad declarada a mano. No hay variable de
entorno que fuerce «misma máquina».

**Encaje (AC5, AC7).** `fit.py` es una función pura:
`requerido = size_en_disco × k + margen_de_contexto(num_ctx)`, con `k` y el margen
constantes documentadas: `k = 1.2` y un margen fijo por cada 1.000 tokens de `num_ctx`,
donde `num_ctx` es el que usa **realmente** el adapter de cada agente al llamar al modelo
(hoy 4096 en formateador, redactor y revisor), no un valor global (valor concreto fijado en el código con su justificación). Son deliberadamente conservadoras,
para no proponer un modelo que no carga, y no son configurables por la persona; se ajustan
más adelante con medidas (p. ej. del harness de SPEC-025). Compara con la VRAM libre y la RAM
libre y devuelve la clase (`fits_gpu`, `fits_partial`, `fits_cpu`, `does_not_fit`). Cada
agente se evalúa contra la memoria total porque corren en secuencia con `keep_alive=0`
(los cuatro adapters actuales lo usan; el valor por defecto del dispatcher es `-1`, así que un
agente genérico que no lo fije puede dejar su modelo cargado, y la sugerencia lo avisa).

**Recomendación (AC6, AC12).** `advisor.py` recibe el inventario, el hardware y el **perfil
de rol** de cada agente y devuelve una lista de sugerencias con su motivo. El perfil de rol
es un dato del proyecto, declarado en el `.agent.md` de cada agente
(`model_profile: reasoning | writing | light`), junto al bloque `models:`, y **validado al
cargar el proyecto** (valor desconocido → error al cargar, no a mitad de la ejecución). No es
una constante en Python. Regla base: entre
los modelos que caben, los roles `reasoning` y `writing` prefieren el de **más parámetros**
que quepa en GPU; `light` prefiere el más pequeño suficiente y deja memoria libre. Si
SPEC-025 aporta una puntuación para ese modelo y rol, se muestra como dato **adicional** con
su procedencia y no cambia la regla.
`model_profile` es **opcional**: un agente sin perfil (p. ej. el publicador, que no llama al
LLM) no recibe sugerencia y la pantalla lo indica como «no usa modelo».

**Aplicar (AC8, AC9).** `agent_settings` **no se persiste**: llega con cada petición y se
rellena desde el perfil del agente (`routers/agents.py`, con filtro por `project_id`). Lo que
persiste por proyecto es `AgentProfileModel.model`, así que aceptar una sugerencia escribe
**ese campo del proyecto activo**, y `resolve_agent_model` no cambia. Un `model` que la
interfaz envíe en la propia petición sigue mandando (primer escalón de la cascada), y la
pantalla lo avisa.

El **origen** no tiene columna propia (vía sin migración). Al aceptar, el registro de auditoría
existente guarda `{proyecto, agente, modelo, quién, cuándo}`. Al cerrar cada paso, si el modelo
resuelto coincide con la última aceptación auditada de ese agente y proyecto, el paso anota
`model_source=recommendation_accepted` **dentro de `params`** (variables de contexto de
`platform/explainability.py`, sin tocar a los agentes). `params` ya entra en el hash de
integridad y añadir una clave dentro no cambia la lista de campos canónicos, así que no hace
falta subir `CANON_VERSION`. Límite: si la persona fija a mano el mismo modelo después de
aceptar, se sigue etiquetando como aceptado; es una etiqueta de procedencia, no una prueba.

**API** (todas con `require_redactor` y `get_project_context`; `apply` exige el mismo rol y acceso
que editar el perfil del agente —no hay un rol de administración de proyecto aparte— y deja
rastro en la auditoría):
- `GET /ai/ollama/models` — inventario con encaje.
- `GET /ai/ollama/hardware` — `HardwareReport`.
- `GET /ai/ollama/recommendations` — sugerencias por agente del proyecto activo.
- `POST /ai/ollama/recommendations/apply` — `{agent, model}`; valida que el modelo esté
  instalado y que la sugerencia corresponda al estado actual.

**Frontend (AC11).** Una vista en `platform/` (no importa de `projects/`) con el sistema de
diseño de SPEC-003. Los roles de los agentes llegan por un registro, como `setAgentCatalog`.

## 5. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Medir el hardware del backend cuando Ollama está en otra máquina | Alto: recomendaciones equivocadas | Solo se mide si la URL es local; si no, `unavailable` o capacidad declarada (AC3, AC4) |
| Estimación de «cabe» demasiado optimista o pesimista | Medio: modelo que no carga o infrautilizado | Constantes documentadas, clase `fits_partial` explícita, y `/api/ps` como comprobación |
| Se presenta la heurística como calidad | Alto: decisión científica sin base | Rótulo obligatorio (AC12), motivo siempre visible, cita de SPEC-025 con procedencia |
| La sugerencia queda obsoleta (otro modelo cargado, VRAM ocupada por otro proceso) | Medio | `apply` revalida contra el estado actual; la VRAM libre se lee en cada consulta, no se cachea |
| Cambiar el modelo cambia el resultado y nadie lo sabe | Alto | El origen queda en la traza (AC9) y en auditoría |
| Utilidad de GPU no instalada o con salida distinta por fabricante | Bajo | Cada lectura es opcional; sin utilidad → `unavailable` |

## 6. Plan de pruebas

- **Unitarias:** `fit.py` con tablas de casos (cabe, parcial, no cabe, límites exactos) y
  determinismo (AC5, AC7); parseo del inventario con y sin `details` (AC1); `HardwareReport`
  con la utilidad ausente, con salida mal formada y con capacidad declarada (AC2–AC4);
  validación de la configuración (AC4).
- **Integración:** endpoints con Ollama sustituido por un doble (`/api/tags`, `/api/ps`),
  proveedor distinto de Ollama (AC10), aislamiento por proyecto, `apply` que rechaza un
  modelo no instalado o una sugerencia obsoleta (AC8).
- **Cascada:** tras `apply`, `resolve_agent_model` devuelve el modelo elegido; sin `apply`,
  no cambia (AC8). Test de que una ejecución no usa una sugerencia sin aceptar.
- **Traza:** el paso registra `model_source` (AC9).
- **Frontend:** `npm run build` y `npm run build:public`; revisión manual de teclado, foco y
  estados (AC11), porque el repo no tiene tests de componentes.
- **No se prueba contra una GPU real en CI.** Una comprobación manual en la máquina del
  mantenedor, con y sin GPU, queda como paso de la tarea de pruebas.

## 7. Impacto operativo / observabilidad

- **Configuración nueva:** `OLLAMA_VRAM_GB` y `OLLAMA_RAM_GB` (opcionales, validadas al cargar
  la configuración). Se documentan en `.env.example` y `config.yaml`.
- **Sin migración:** la elección va en `AgentProfileModel.model` y el origen en `params` del
  paso y en la auditoría. Si se quisiera mostrar el origen sin consultar la auditoría, haría
  falta una columna y su migración Alembic (alternativa descartada por ahora).
- **Datos y retención:** no se guarda histórico de hardware; si se añade una tabla, se
  actualiza `docs/governance/data-retention.md` (hay un test que lo comprueba).
- **Observabilidad:** log de la clase de encaje y de la fuente del hardware; el modelo y su
  origen ya van en la traza (SPEC-014).
- **Rollback:** no aceptar sugerencias deja el comportamiento actual; revertir una elección
  es fijar de nuevo el modelo del agente.

## 8. Backlog (sincronización SDD)

```yaml
# sdd-sync v1
epic:
  id: E30
  title: "Recomendación de modelos Ollama por agente según hardware"
  area: area/backend
tasks:
  - id: T30.1
    title: "Inventario de modelos Ollama con tamaño, familia y cuantización"
    sev: medium
    depends_on: []
    acceptance: [AC1, AC10]
  - id: T30.2
    title: "Detección de VRAM y RAM libres, capacidad declarada y estado «sin datos»"
    sev: high
    depends_on: []
    acceptance: [AC2, AC3, AC4]
  - id: T30.3
    title: "Estimador de encaje de un modelo en la memoria disponible"
    sev: high
    depends_on: [T30.1, T30.2]
    acceptance: [AC5, AC7]
  - id: T30.4
    title: "Recomendador por agente; model_profile en los .agent.md, validado al cargar el proyecto"
    sev: high
    depends_on: [T30.3]
    acceptance: [AC6, AC7, AC12]
  - id: T30.5
    title: "Aplicar sugerencia con confirmación (perfil del proyecto), auditoría y origen en params de la traza"
    sev: high
    depends_on: [T30.4]
    acceptance: [AC8, AC9]
  - id: T30.6
    title: "Frontend: pantalla de hardware, modelos y sugerencias por agente"
    sev: medium
    depends_on: [T30.4, T30.5]
    acceptance: [AC11, AC12]
  - id: T30.7
    title: "Tests, comprobación manual con y sin GPU y documentación de la configuración"
    sev: medium
    depends_on: [T30.5]
    acceptance: [AC1, AC5, AC8, AC10]
```
