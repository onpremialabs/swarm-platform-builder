# SPEC-032: Compuerta de publicación según el Framework de validación (Fase 1)

- **Estado:** In progress
- **Autor:** Equipo de plataforma (borrador asistido)
- **Fecha:** 2026-10-21 · paso a `Ready` tras `/speckit-clarify`, `/speckit-checklist` (33/43) y `/speckit-analyze`
- **Épica:** E20 (GitHub Project)
- **ADR relacionado:** [ADR-0011](../adr/0011-publication-gate-fail-closed.md) · enmendado en parte por [ADR-0013](../adr/0013-author-supplied-sources-and-deferred-verification.md) (V09 y AC8)
- **Severidad:** 🔴

> **Origen.** Plan de implementación de mejoras del pipeline, Fase 1 (tareas 1.1–1.9), a
> partir del *Framework de redacción y validación de papers* v0.1 (29/09/2026) y del
> diagnóstico de código de [`docs/reports/matriz-implementacion.md`](../reports/matriz-implementacion.md).
> Cierra los hallazgos H-01 (referencias incompletas / `(Author, Year)`) y H-03 (sin
> compuerta ni aprobación humana). El framework es la fuente de la verdad de las reglas;
> esta spec solo decide cómo se implementan aquí. Cita sus secciones como «FW §n».

## 1. Problema

Hoy ningún manuscrito con defectos verificables está impedido de llegar a «Publicado»:

- `backend/app/modules/agents/adapters/publicador.py` (`run_publicador`) escribe el texto en
  la BD y marca `PUBLISHED` **sin validar nada**. No existe compuerta (FW §3 etapa 8).
- **Hay tres caminos a `PUBLISHED` y ninguno valida:** el agente Publicador; `approve`
  (`routers/articles.py`), que solo guarda `reviewer_id` y `published_at`, no la versión
  aprobada; y `POST /articles/{id}/publish` (`publish_article_direct`, usado por
  `frontend/.../articleStore.js`), que publica un borrador directamente con rol admin o
  redactor.
- **Falla abierto el Revisor** (`revisor.py`): sin JSON válido deja `approval_score = 85` y
  aprueba; si el LLM falla, inventa una revisión (75 y 90 con comentarios fijos).
- Tras agotar las 3 vueltas, `platform/engine/routing.py` (`make_review_router`) **avanza
  igualmente** a Formateador y Publicador. FW §3 exige el estado «requiere revisión humana»
  y no publicar.
- Las referencias salen de RAG local con `doi`, `year`, `journal` y `url` siempre vacíos
  (`investigador.py`), y `format_source_deterministic` (`formateador.py`) **omite** los campos
  que faltan en lugar de fallar, de modo que un nombre de archivo acaba como «referencia»
  (H-01). Nada comprueba que exista (FW §7, niveles 1 y 2).
- El «modelo» que aparece en la traza del Publicador es un artefacto: `use_cases.py`
  rellena `model` para **todos** los agentes aunque no llamen al LLM.

El framework fija que se publica solo si se cumplen **tres** condiciones: (1) Revisor ≥ 80 sin
bloqueantes de juicio abiertos, (2) compuerta determinista sin bloqueantes sobre el **texto
final tras el Formateador**, (3) aprobación humana explícita (FW §3, regla de decisión).

## 2. Objetivos / No-objetivos

- **Objetivos**
  - Compuerta determinista, sin LLM, en el Publicador, sobre el texto final.
  - Detector de marcadores de posición y validación de estructura y existencia de
    referencias (V09) contra Crossref/OpenAlex, **con falla cerrada**.
  - Informe de compuerta persistido y versionado por texto evaluado.
  - Estado «requiere revisión humana» tras 3 vueltas con bloqueantes.
  - Aprobación humana explícita, registrada, que vincula usuario, decisión, fecha y versión.
  - **Una sola puerta a `PUBLISHED`**: el agente, `approve` y `publish` consultan la misma
    función de decisión.
  - Publicador sin LLM, también en la traza.
- **Decisión de V09 (opción «a», sin excepciones; ver ADR-0011).** Cada documento que alimenta
  Referencias se **resuelve contra Crossref/OpenAlex por DOI o, si no lo tiene, por título y
  autores**, y se verifica la coincidencia de título, autores, año y revista. Lo que no se
  resuelve queda **«no verificado»** y bloquea. El autor puede **aportar el DOI a mano**
  (metadato `doi` del documento, con registro de quién y cuándo), que entra por el mismo
  camino de verificación. *Se descartan* la excepción para «documento interno» (FW §2.4, §7
  nivel 1) y la entrada solo por búsqueda externa (es la Fase 4).
  **Enmienda 2026-11-23 (ADR-0013):** la excepción deja de descartarse sin más. Una persona puede
  declarar un documento «aportado por el autor» (sin identificador); V09 lo etiqueta y su severidad
  es `gate.references.author_supplied` (`block` por defecto; un proyecto puede declarar `warn`).
  Un DOI declarado que no resuelve o no coincide **sigue bloqueando** (AC17).
- **No-objetivos**
  - Salida del Revisor **por criterio** y cambio de modelo (Fase 3). Aquí solo se corrige que
    falle abierto y se define cómo cuenta su resultado en la decisión (AC15).
  - **Devolución automática** del manuscrito al agente responsable del criterio que falla
    (Fase 2, contratos entre agentes): en esta fase la persona reejecuta (AC14).
  - Búsqueda bibliográfica externa, ficha de estudio, protocolo sellado y registro de
    búsqueda (Fase 4); declaraciones de IA, CRediT, conflictos y FAIR (Fase 5).
  - V10 (soporte de la cita), V11 (retractaciones: exige una fuente abierta que no hay aún),
    V15 y V02: son de juicio o necesitan herramientas de fases posteriores.
  - Contratos/esquemas por agente y enrutado de comentarios (Fase 2).
  - Control de similitud textual/plagio (decisión abierta del panel, FW §19).
- **Glosario** (términos canónicos de esta spec)
  - **Bloqueante determinista:** un criterio de la compuerta con resultado `failed` o
    `not_verified`.
  - **Bloqueante de juicio** (definición provisional de la Fase 1, hasta que la Fase 3 dé
    salida por criterio): la revisión **no aprueba**, es decir, `approval_score < 80`, o
    `coherent = false`, o `review_status = not_verified` (el Revisor no pudo producir una
    revisión interpretable).
  - **Resultado de un criterio:** `passed`, `failed`, `not_verified` o `not_implemented`
    (siempre en inglés, snake_case, igual que el estado de los artículos: `draft`,
    `in_review`, `requires_human_review`, `approved`, `published`, `rejected`).

## 3. Criterios de aceptación (Given/When/Then)

- [ ] **AC1** — *Marcadores de posición* *Given* un texto final que contiene alguno de estos
  patrones, y solo estos: `(Author, Year)`, `(Autor, Año)`, `(Author et al., Year)`, `[?]`,
  `[??]`, `[citation needed]`, `[cita necesaria]`, `TODO`, `TBD`, `XXX` · *When* corre la
  compuerta · *Then* hay un resultado **bloqueante** que nombra el patrón y su posición, y el
  artículo no pasa a `published`. Se ignora el texto dentro de bloques de código delimitados
  (``` ```) y de código en línea (`` ` ``), de modo que un manuscrito que *hable de* esos
  marcadores puede citarlos entre comillas de código. La lista vive en `template.yaml`
  (`gate.placeholders`) y se amplía allí.
- [ ] **AC2** — *Estructura de referencias* *Given* las referencias del texto final **después
  de resolver y enriquecer** (AC3) · *When* corre la compuerta · *Then* una referencia sin
  identificador, sin autores, sin año o sin publicación (p. ej. solo un nombre de archivo) es
  **bloqueante** e indica qué campo falta. El orden es siempre: resolver y enriquecer,
  después validar la estructura. Un campo vacío ya no se omite en silencio al formatear.
- [ ] **AC3** — *Existencia y coincidencia (V09)* *Given* una referencia con DOI, o sin él pero
  con título y autores · *When* se resuelve contra Crossref y, si no aparece, OpenAlex ·
  *Then* pasa solo si existe y coinciden título (similitud ≥ 0,90), primer autor y al menos la
  mitad de los demás, año (±1 solo preprint↔publicada con el mismo DOI) y revista, con
  umbrales en `template.yaml` (`gate.references`); una discrepancia es bloqueante, y una
  referencia sin resolver o con varios candidatos igualmente plausibles es `not_verified` y
  también bloquea. Si el autor aporta un DOI, se verifica por este mismo camino. **Objetivo
  medible:** sobre el conjunto de prueba de referencias reales con DOI, se resuelve y pasa al
  menos el 90 %.
- [ ] **AC4** — *Falla cerrada* *Given* que Crossref y OpenAlex no responden (error, tiempo
  agotado o respuesta inválida) · *When* corre la compuerta · *Then* las referencias quedan
  `not_verified`, el criterio **no se aprueba** y el motivo consta en el informe. Valores
  iniciales, configurables en `gate.references`: 10 s por consulta, 2 reintentos con espera
  exponencial, 120 s como máximo por evaluación; la caché guarda **solo resultados positivos**
  con TTL de 30 días. Nunca se aprueba por ausencia de respuesta.
- [ ] **AC5** — *Posición y alcance de la compuerta* *Given* un flujo completo · *When*
  termina el Formateador · *Then* la compuerta se evalúa sobre `formatted_text` (el texto
  que se publicaría), no sobre el borrador, y cada criterio del conjunto en vigor obtiene
  exactamente uno de: `passed`, `failed`, `not_verified`, `not_implemented`. Solo `failed` y
  `not_verified` bloquean; `not_implemented` **no** bloquea y el informe lo lista como
  pendiente con la fase que lo construye.
- [ ] **AC6** — *Informe persistido* *Given* una evaluación de la compuerta · *When* termina ·
  *Then* se guarda un informe con estado y evidencia por criterio, la huella (SHA-256) del
  texto evaluado, la fecha y la ejecución, y se puede leer por API y verlo desde el artículo.
  Una nueva evaluación crea otro informe: no sobrescribe el anterior. Existe una acción para
  **reevaluar** el texto actual, y el informe vigente es el último cuyo hash coincide con el
  cuerpo. Los artículos anteriores a esta spec **no tienen informe**: se muestran «sin
  informe» y los ya `published` no se tocan.
- [ ] **AC7** — *Revisión humana tras 3 vueltas* *Given* que se agotan las 3 vueltas y la
  revisión sigue sin aprobar (bloqueante de juicio, ver Glosario) · *When* el enrutador decide
  el siguiente paso · *Then* el artículo pasa a `requires_human_review`, **no** se ejecutan
  Formateador ni Publicador y se emite el evento SSE `requires_human_review`, con puntuación y
  comentarios. Solo una persona sale de ese estado: reejecutar (→ `draft`, con las vueltas
  reiniciadas y los comentarios visibles) o `reject` (→ `rejected`). Una reanudación
  (`resume`) no reinicia el contador.
- [ ] **AC8** — *Aprobación humana explícita* *Given* una compuerta sin bloqueantes · *When* el
  Publicador termina · *Then* el artículo queda en `in_review` y **nunca** en `published`.
  `approve` registra usuario, decisión, fecha y huella del texto aprobado; se rechaza con
  409 si el texto cambió desde la compuerta o si el último informe tiene bloqueantes o si el
  artículo no tiene autor responsable declarado, y con 403 si quien aprueba es el propietario
  del artículo (quien lanzó el pipeline) o no es el revisor asignado ni un administrador. Solo
  con `DEBUG` activo y `PUBLICATION_ALLOW_SELF_APPROVAL=true` se permite la autoaprobación,
  para entornos de un solo usuario; nunca en producción **salvo que el proyecto declare
  `approval.allow_self_approval: true` en su plantilla (ADR-0013, AC18)**.
- [ ] **AC9** — *Publicador sin LLM* *Given* una ejecución completa · *When* corre el Publicador ·
  *Then* no llama al LLM (0 tokens) y su traza no registra modelo (`model` nulo), a diferencia
  de hoy. Un agente declara que no usa LLM al no pedir las capacidades `llm`/`llm_stream` en
  `template.yaml`; la traza usa esa declaración. Un test falla si el módulo importa o invoca
  `call_llm`.
- [ ] **AC10** — *Regla de decisión unificada* *Given* los tres insumos (revisión, compuerta,
  aprobación) · *When* se evalúa si publicar · *Then* una sola función (`can_publish`) decide,
  y solo devuelve «publicar» con revisión que aprueba (≥ 80 y sin bloqueante de juicio),
  compuerta sin bloqueantes y aprobación humana. Un 80 con un bloqueante abierto no publica.
  Es verificable porque `can_publish` es el **único** punto del código que asigna `published`
  (un test lo comprueba por inspección estática).
- [ ] **AC11** — *Estructura IMRaD (V03)* *Given* un texto final sin alguna de las secciones
  Introducción, Métodos, Resultados, Discusión o Referencias, o con ellas fuera de orden, o
  con Resultados y Discusión fundidos · *When* corre la compuerta · *Then* V03 es `failed`
  y nombra la sección ausente o desordenada. Los títulos aceptados por sección salen de un
  diccionario por idioma en `template.yaml` (`gate.structure`), p. ej. «Métodos» y
  «Metodología» para es, y «Methods» para en. El Redactor produce Resultados y Discusión como
  secciones separadas.
- [ ] **AC12** — *Regresión* *Given* un manuscrito válido con referencias resueltas · *When*
  recorre el pipeline y recibe aprobación · *Then* llega a `published`, la suite no tiene
  **ningún fallo nuevo** respecto a `develop` (hoy hay 4 preexistentes) y el gate EDD no
  regresa, o su regresión está explicada y aceptada en la propia PR.
- [ ] **AC13** — *Una sola puerta a `published`* *Given* cualquiera de los caminos a
  `published` (agente, `approve`, `POST /articles/{id}/publish`) · *When* se intenta publicar ·
  *Then* todos consultan `can_publish`. `publish` evalúa la compuerta sobre el texto actual
  si no hay informe vigente y aplica las mismas reglas de aprobación que `approve`; un
  artículo sin compuerta aprobada no puede publicarse por ninguno de los tres.
- [ ] **AC14** — *Compuerta con bloqueantes* *Given* una compuerta con algún bloqueante ·
  *When* el Publicador termina · *Then* el artículo pasa a `draft`, el informe indica por cada
  bloqueante el criterio, la evidencia y el **agente responsable** (Fase 2 lo automatizará) y
  se emite un evento SSE `gate_failed`. No se publica ni se envía a revisión; la persona
  corrige y reejecuta o reevalúa (AC6).
- [ ] **AC15** — *Revisor que no aprueba por defecto* *Given* que el Revisor no devuelve un JSON
  interpretable o el LLM falla · *When* termina el paso · *Then* `review_status` es
  `not_verified`, cuenta como bloqueante de juicio y **no** se inventa ninguna puntuación ni
  comentarios; se elimina el 85 por defecto y la revisión simulada. El mismo caso se prueba
  con una respuesta válida para fijar que sigue funcionando.
- [ ] **AC16** — *Despliegue gradual y privacidad* *Given* `PUBLICATION_GATE_ENFORCE=false` ·
  *When* corre la compuerta · *Then* los resultados `failed` y `not_verified` se registran y
  se avisan, pero no impiden que el flujo llegue a aprobación humana (que sigue siendo
  obligatoria); con `true` (valor por defecto) bloquean. En ambos modos, a Crossref/OpenAlex
  solo se envían **metadatos de referencias** (nunca el texto del manuscrito) y por la puerta
  `platform/egress.py`; si `EGRESS_ALLOWED_DOMAINS` está definida, `api.crossref.org`,
  `api.openalex.org` y `api.datacite.org` (DOI de arXiv) se añaden a ella.
- [ ] **AC17** — *Fuentes aportadas por el autor (ADR-0013)* *Given* una referencia cuyo documento
  la persona autora ha declarado «aportado por el autor» (sin identificador), con registro de
  quién y cuándo · *When* corre V09 · *Then* **no** se consulta Crossref/OpenAlex/DataCite por ella
  y su estado es `author_supplied`, con la severidad de `gate.references.author_supplied`:
  `block` (por defecto: bloquea, como hoy) o `warn` (no bloquea, el informe la lista una a una,
  Referencias la etiqueta «documento aportado por el autor, sin identificador» y el informe dice que
  su retractación no se pudo comprobar). Su estructura mínima exige autores, año, título o nombre
  del documento y tipo de documento, en lugar del identificador. *And* un documento con **DOI
  declarado** que no resuelve o no coincide es bloqueante en ambos casos (no pasa a esta clase), y
  solo una persona puede declarar la clase: ni el sistema ni el modelo. *And* un proyecto que no
  declara `author_supplied` se comporta exactamente como antes. El valor se valida al cargar la
  plantilla.
- [ ] **AC18** — *Autoaprobación por proyecto (ADR-0013)* *Given* un proyecto con
  `approval.allow_self_approval: true` · *When* quien lanzó el pipeline aprueba su artículo *Then*
  se permite, **sin** relajar el resto: el Revisor, la compuerta, `requires_human_review`, el 409
  por texto cambiado o con bloqueantes y la exigencia de autor responsable declarado se aplican
  igual; el registro de aprobación guarda `self_approved=true` y el informe de compuerta lo dice
  («sin revisión independiente»). *And* sin esa declaración (valor por defecto `false`) rige el 403
  de AC8. El valor se valida al cargar la plantilla y no lo cambia la persona autora por artículo.
  El interruptor global `PUBLICATION_ALLOW_SELF_APPROVAL` (solo con `DEBUG`) no cambia.

## 4. Diseño propuesto

**Módulo de compuerta** `backend/app/platform/publication_gate/` (genérico, no nombra agentes):
un registro de criterios, cada uno una función pura `(contexto) -> CriterionResult`. El
Publicador la invoca; el proyecto declara en `template.yaml` (`gate:`) qué criterios se
aplican y con qué parámetros, igual que `flow_rules` (declaradas en `template.yaml` y
validadas al cargar por `platform/projects/loader.py`, ver `docs/bitacora/tarea-411.md`).
Así la compuerta no vive en código disperso y otro proyecto puede traer la suya.

- **Orden de evaluación:** 1) resolver y enriquecer referencias (AC3), 2) validar su
  estructura (AC2), 3) marcadores (AC1), 4) estructura IMRaD (AC11), 5) criterios
  `not_implemented`. Los criterios sin LLM van antes que cualquier juicio (FW §20).
- **Criterios de esta fase:** marcadores, estructura de referencias (V09 nivel 1), existencia
  (V09 nivel 2) y estructura IMRaD (V03). Los criterios cuyos datos aún no existen (V01,
  V05–V08, V12–V14, V16) se **declaran** y resultan `not_implemented` hasta que su fase los
  construya.
- **Resolución de referencias** (`reference_resolver.py`): cliente a Crossref y OpenAlex por
  la puerta de salida única `platform/egress.py` (`safe_get`), como exige SPEC-024. Parámetros
  de AC4 y AC3 en `gate.references`.
- **Fuentes con identificador.** El Investigador deja de dejar `doi/year/journal` vacíos:
  conserva lo que el documento traiga (incluido el `doi` aportado a mano) y, al resolver,
  **enriquece** la fuente con los metadatos canónicos; el Formateador **falla** en lugar de
  omitir un campo y solo imprime fuentes completas.
- **Datos (migración Alembic, con test de paridad `create_all`/migraciones):**
  - tabla `publication_gate_reports`: `article_id`, `run_id`, `text_sha256`, `criteria` (JSON),
    `created_at`;
  - en el artículo: `responsible_author_id` (FK a usuarios, nulo hasta que se declara),
    `approved_by`, `approved_at`, `approved_text_sha256`;
  - nuevo valor `requires_human_review` de `ArticleStatus`.
  - Retención del informe: mientras exista un artículo `published`; para los demás, 90 días,
    alineado con `agent_runs` (`RETENTION_GATE_REPORTS_DAYS`), documentado en
    `data-retention.md`.
- **API:** `GET /api/v1/articles/{id}/gate-report` (autor, revisor asignado o admin) y
  `POST /api/v1/articles/{id}/gate-report` (reevaluar). El informe solo lo escribe el backend;
  su huella impide aprobar un texto distinto del evaluado.
- **Enrutador:** al agotar vueltas con revisión rechazada, `routing.py` devuelve el fin en
  lugar de `next_after(...)` y la ejecución marca `requires_human_review`; reejecutar lo
  devuelve a `draft` y reinicia `loop_count`.
- **Una sola puerta:** `can_publish(review, gate, approval)` es la única función que asigna
  `published`; la usan el Publicador, `approve` y `publish`.
- **Revisor:** `review_status` (`ok`/`not_verified`) sustituye al 85 por defecto; el campo
  alimenta `can_publish`.
- **Traza:** `use_cases.py` registra `model = null` para agentes que no piden capacidades LLM.
- **Ficheros afectados:** `adapters/publicador.py`, `adapters/revisor.py`,
  `adapters/investigador.py`, `adapters/formateador.py`, `adapters/redactor.py` (prompt:
  separar Resultados y Discusión), `platform/engine/routing.py`,
  `application/use_cases.py`, `routers/articles.py`, `models/`, `alembic/versions/`,
  `projects/alejandria-magazine/template.yaml`, `platform/projects/loader.py`,
  `core/config.py`, `evals/agent_behavior/` (datasets y `thresholds.yaml`), frontend (estado
  del artículo, informe y aprobación), `docs/governance/data-retention.md`.

### Impacto de seguridad (DoR §5)

- **Egress:** dos hosts nuevos, por `safe_get`; se revalidan las redirecciones (SPEC-024).
- **Datos:** salen solo metadatos de referencias ya citadas, no el texto ni datos personales.
- **Autorización:** `approve` y `publish` comparten reglas (revisor asignado o admin, distinto
  del propietario); la autoaprobación solo existe con `DEBUG`.
- **Integridad:** el informe lo escribe solo el backend y queda ligado al texto por su huella;
  `approve` rechaza un texto cambiado.
- **Secretos:** ninguno; las APIs son públicas (se recomienda identificar el cliente con un
  correo de contacto, que va en configuración, no en el repositorio).

## 5. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Con falla cerrada y criterios aún no construidos, **nada podría publicarse** | Bloqueo total del flujo | `not_implemented` no bloquea; bloquean ya marcadores, V03, V09 y la decisión unificada (ADR-0011); cada fase lo retira al implementar su criterio |
| Documentos subidos a mano sin DOI no se resuelven por título | Falsos `not_verified` | El autor aporta el DOI; el informe indica el motivo; se mide la tasa de resolución (AC3) |
| Falsos positivos de coincidencia (títulos parecidos) | Referencia correcta bloqueada | Umbrales configurables (0,90 de partida), evidencia en el informe y revisión humana final |
| Crossref/OpenAlex lentos o caídos | Publicación detenida | Caché de positivos, tiempo máximo y reintentos (AC4); falla cerrada explícita; modo de despliegue (AC16) |
| Enviar títulos de manuscritos no publicados a un servicio externo | Privacidad | Solo metadatos de referencias (AC16); se revisan las condiciones de uso (FW §20.7) |
| Flujos y artículos existentes que quedarían bloqueados | Regresión | `PUBLICATION_GATE_ENFORCE=false` al desplegar; los `published` previos no se tocan (AC6) |
| Cambiar `ArticleStatus` rompe el frontend o filtros | Errores en listados | Migración, test de paridad y revisión de todos los usos del enum |
| El Revisor deja de aprobar por defecto y cambia el comportamiento medido | Regresión EDD no explicada | Datasets golden/regressions y umbrales actualizados en la misma PR (§6) |
| `publish` directo seguía siendo un atajo | La compuerta se puede saltar | AC13: pasa por `can_publish`, con test estático de único punto de asignación |

## 6. Plan de pruebas

- **Unitarias (código determinista, sin muestreo, FW §14):** un caso válido y uno inválido por
  criterio — AC1 (PR-REG-01), AC2 (PR-REG-02), AC3, AC11, y AC10 (tabla de verdad completa de
  `can_publish`).
- **Falla cerrada:** resolutor simulado que lanza error/tiempo agotado → `not_verified` y
  no aprueba (AC4, PR-REG-12).
- **Integración:** flujo completo con resolutor simulado: referencia válida pasa, inventada
  falla, sin DOI y sin título resoluble queda no verificada, DOI aportado a mano se verifica
  (AC3); el artículo no llega a `published` sin `approve` (AC5, AC6, AC8, PR-REG-05/06); 3
  vueltas con bloqueantes no ejecuta el Formateador (AC7); compuerta con bloqueantes devuelve
  a `draft` (AC14); `approve` con texto cambiado → 409, propietario → 403 (AC8).
- **Una sola puerta (AC13):** un test recorre los tres caminos; otro inspecciona el código y
  falla si algo distinto de `can_publish` asigna `published`.
- **Revisor (AC15):** respuesta no interpretable y error del LLM → `not_verified`, sin 85 ni
  revisión inventada.
- **Publicador sin LLM:** test estructural y de traza (AC9, PR-REG-11).
- **Migración:** `tests/test_migrations.py` verifica que el esquema migrado coincide con
  `create_all`; `test_data_retention.py` cubre la tabla nueva.
- **Evaluación (EDD, GOVERNANCE §5/§6, `edd-discipline.md`):** esta spec cambia Revisor,
  Redactor, Formateador e Investigador. En la misma PR se actualizan `revisor-*`,
  `redactor-*`, `formateador-*` e `investigador-*` en `evals/agent_behavior/datasets/` y, si
  procede, `thresholds.yaml`; se corre `python -m evals.agent_behavior.gate` y cualquier
  regresión queda explicada y aceptada en la PR.
- **Regresión (AC12):** suite completa sin fallos nuevos; los 4 preexistentes no empeoran.
- Las definiciones de PR-REG-xx viven en el informe de pruebas, que no está en el repositorio:
  se enlazan por ID. Mapa AC↔PR-REG: AC1→01, AC2→02, AC4→12, AC5/AC8→05, 06, AC9→11,
  AC10 y AC15→04.

## 7. Impacto operativo / observabilidad

- Logs y métricas: resultado por criterio, aciertos de caché y tasa de `not_verified` por
  motivo; latencia y errores de Crossref/OpenAlex (incluido 429).
- Nueva tabla y columnas: migración Alembic; retención documentada en `data-retention.md`
  (AC6, §4).
- Despliegue: `PUBLICATION_GATE_ENFORCE=false` primero (registra y avisa), luego `true`.
  Rollback: volver a `false` y, si hace falta, a la migración previa.
- Cambio de comportamiento visible: los artículos ya no quedan `published` al terminar el
  pipeline; pasan a `in_review`, `draft` o `requires_human_review`.
- Límites de uso de las APIs externas: se respeta el *polite pool* de Crossref y OpenAlex
  (identificación por correo en configuración) y se trata un 429 como `not_verified` con
  espera, sin insistir.

## Clarifications

### Session 2026-10-21

- Q: ¿Qué criterios bloquean desde la Fase 1, si V01, V05–V08, V12–V14 y V16 no tienen datos hasta las Fases 4 y 5? → A: `not_implemented` es un estado propio que **no bloquea** y se lista en el informe como pendiente; bloquean desde ya marcadores de posición, estructura (V03), referencias (V09) y la decisión unificada.
- Q: ¿Qué cuenta como «coincidencia» de una referencia en V09? → A: **título** con similitud normalizada ≥ 0,90; **autores**: coincide el apellido del primer autor y al menos la mitad de los demás; **año** exacto, o ±1 solo si es preprint↔versión publicada con el mismo DOI; **revista** coincidente tras normalizar alias y abreviaturas. Los umbrales viven en `template.yaml` (`gate.references`), no en código.
- Q: ¿Quién puede aprobar la publicación? → A: un **humano distinto del usuario que lanzó el pipeline**: el revisor asignado o un administrador (como hoy). El registro guarda quién firma, y el artículo debe tener un **autor responsable** declarado (V13); sin él no se puede aprobar.
- Q: ¿Qué estructura valida V03 sin ficha de estudio? → A: **IMRaD por defecto** (Introducción, Métodos, Resultados, Discusión y Referencias, en ese orden). Se cambia el prompt del Redactor para separar Resultados y Discusión (hoy van fundidos). Con la ficha (Fase 4) V03 leerá el perfil que ella declare, con el mismo mecanismo.
- Q: ¿Cómo se llama el estado de «requiere revisión humana» y cómo se sale de él? → A: valor `requires_human_review` de `ArticleStatus`. Solo sale por una persona: o reejecuta el pipeline (vuelve a `draft`, con el contador de vueltas reiniciado y los comentarios del Revisor visibles) o lo rechaza con `reject` (pasa a `rejected`). No hay salida automática.

### Session 2026-10-21 (análisis)

Correcciones derivadas de `/speckit-analyze` y del checklist, sin cambiar las decisiones de arriba:

- El análisis halló un tercer camino a `published` (`POST /articles/{id}/publish`): se añade AC13.
- Se define el «bloqueante de juicio» provisional de la Fase 1 y se separa el Revisor que no aprueba por defecto (AC15) de la decisión unificada (AC10).
- Se resuelve el orden «resolver y enriquecer, luego validar estructura» (AC2/AC3) y la ruta de la compuerta con bloqueantes (AC14).
- Se fijan los valores iniciales de la falla cerrada, los patrones de marcador y el objetivo de resolución.
- La decisión de política queda registrada en ADR-0011; el plan de pruebas incorpora la evaluación EDD.

### Session 2026-10-21 (implementación y medición)

Hechos y decisiones que salieron de implementar E20 y de medir AC3 contra Crossref/OpenAlex reales ([informe](../reports/medicion-ac3-spec-032.md)); no cambian los criterios de aceptación. Lo que sigue abierto está en [spec-032-decisiones-pendientes.md](../reports/spec-032-decisiones-pendientes.md).

- Un manuscrito **sin referencias estructuradas** deja `reference_existence` en `not_verified` y bloquea (CHK034): no se aprueba por ausencia de referencias.
- El **autor responsable** se declara con `PUT /api/v1/articles/{id}/responsible-author` (autor del artículo o admin; usuario activo) (CHK015).
- Con «et al.» en la cita solo se exige el primer autor; sin él, la mitad de los demás (CHK016).
- La revista se compara por palabras significativas, tolerando abreviaturas y palabras genéricas, con un 60 % de coincidencia; sin diccionario (CHK017).
- Si varios registros encajan por título y autores, **el año y la revista de la cita desempatan**; si siguen siendo varios o ninguno, `not_verified`.
- La **revisión** (puntuación, `coherent`, `review_status`) se guarda con el informe de la compuerta, porque `can_publish` la necesita y fuera del pipeline no queda rastro. Sin Revisor en el flujo, `review_status = not_run` y no se publica.
- `publish` ya no lo puede usar el propietario ni quien no sea revisor asignado o admin: aplica las mismas reglas que `approve` (AC13).
- La salida hacia Crossref/OpenAlex es por `safe_get` con `quien="publication_gate"`; con allowlist definida, esos hosts se añaden **solo** para la compuerta.
- **Métricas Prometheus** (CHK037): `publication_gate_criterion_total{criterion,status}`, `publication_gate_reference_total{outcome}` (`cache_hit`, `resolved`, `mismatch`, `not_verified`) y `publication_gate_external_errors_total{provider,reason}`, más un log estructurado por criterio.
- **Medición real:** 18/20 con DOI (90 %, sin margen), 10/12 sin DOI, 6/6 controles negativos bloqueados. Los dos fallos con DOI son de arXiv (DataCite, no Crossref): ver DEC-1.

## 8. Backlog (sincronización SDD)

```yaml
# sdd-sync v1
epic:
  id: E20
  title: "Compuerta de publicación según el Framework de validación (Fase 1)"
  area: area/backend
tasks:
  - id: T20.1
    title: "Detector de marcadores de posición en el texto final"
    sev: high
    depends_on: []
    acceptance: [AC1]
  - id: T20.2
    title: "Formateador que no omite campos, enriquecimiento de fuentes y validador de estructura de referencias"
    sev: high
    depends_on: []
    acceptance: [AC2]
  - id: T20.3
    title: "Resolución de existencia contra Crossref/OpenAlex con falla cerrada (V09 nivel 2)"
    sev: high
    depends_on: [T20.2]
    acceptance: [AC3, AC4]
  - id: T20.4
    title: "Módulo de compuerta, V03 IMRaD y configuración gate en template.yaml con su validación al cargar"
    sev: high
    depends_on: [T20.1, T20.2, T20.3]
    acceptance: [AC5, AC11]
  - id: T20.5
    title: "Redactor: separar Resultados y Discusión en el prompt"
    sev: medium
    depends_on: []
    acceptance: [AC11]
  - id: T20.6
    title: "Migración y modelos: informe, estado requires_human_review, aprobación y autor responsable; API del informe"
    sev: high
    depends_on: [T20.4]
    acceptance: [AC6]
  - id: T20.7
    title: "Revisor que no aprueba por defecto y definición del bloqueante de juicio"
    sev: high
    depends_on: []
    acceptance: [AC15]
  - id: T20.8
    title: "Estado «requiere revisión humana» tras 3 vueltas con bloqueantes"
    sev: high
    depends_on: [T20.6, T20.7]
    acceptance: [AC7]
  - id: T20.9
    title: "Compuerta con bloqueantes devuelve el artículo a draft con informe y agente responsable"
    sev: medium
    depends_on: [T20.4, T20.6]
    acceptance: [AC14]
  - id: T20.10
    title: "Aprobación humana explícita con registro de usuario, decisión, fecha y versión"
    sev: high
    depends_on: [T20.6]
    acceptance: [AC8]
  - id: T20.11
    title: "Una sola puerta a published: can_publish y el endpoint publish directo"
    sev: high
    depends_on: [T20.4, T20.7, T20.10]
    acceptance: [AC10, AC13]
  - id: T20.12
    title: "Publicador sin LLM, también en la traza"
    sev: low
    depends_on: []
    acceptance: [AC9]
  - id: T20.13
    title: "Despliegue gradual, retención de informes y allowlist de egress"
    sev: medium
    depends_on: [T20.6]
    acceptance: [AC16]
  - id: T20.14
    title: "Frontend: estado del artículo, informe de compuerta y aprobación"
    sev: medium
    depends_on: [T20.6, T20.10]
    acceptance: [AC6, AC7, AC8]
  - id: T20.15
    title: "Evaluación EDD: datasets y umbrales actualizados y regresión sin fallos nuevos"
    sev: high
    depends_on: [T20.7, T20.11]
    acceptance: [AC12]
  - id: T20.16
    title: "V09: clase «aportada por el autor» con severidad configurable (gate.references.author_supplied), estructura mínima y etiqueta en Referencias"
    sev: high
    depends_on: [T20.3]
    acceptance: [AC17]
  - id: T20.17
    title: "Autoaprobación por proyecto (approval.allow_self_approval) con registro self_approved y aviso en el informe"
    sev: medium
    depends_on: [T20.10]
    acceptance: [AC18]
```
