# Swarm Platform Builder — v0.2.0

Plataforma de construcción y orquestación de agentes IA construida sobre **FastAPI**, **LangGraph** y **Qdrant**. Permite crear proyectos independientes, cada uno con su propio swarm de agentes configurables, base documental RAG y flujo de trabajo personalizado.

El proyecto de referencia incluido es **AlejandrIA Magazine**: un pipeline de cinco agentes especializados para la investigación, redacción, revisión, formateo y publicación de artículos de revista científica, con soporte de re-ejecución parcial, cancelación en caliente y publicación directa por parte de administradores.

> **¿Te incorporas al proyecto?** Empieza por la guía interactiva
> [`docs/public/onboarding/alejandria-por-dentro.html`](docs/public/onboarding/alejandria-por-dentro.html):
> proyecto, arquitectura explorable, tareas abiertas con sus dependencias y cómo
> ejecutarlas desde la terminal. Ver [Guía para colaboradores](#guía-interactiva-para-colaboradores).

---

## Tabla de contenidos

1. [Stack tecnológico](#stack-tecnológico)
2. [Instalación local](#instalación-local)
3. [Cómo funciona la plataforma](#cómo-funciona-la-plataforma)
4. [Gestión de proyectos y agentes](#gestión-de-proyectos-y-agentes)
5. [Proyecto: AlejandrIA Magazine](#proyecto-alejandria-magazine)
   - [Flujo de redacción de papers](#flujo-de-redacción-de-papers)
   - [Roles y usuarios](#roles-y-usuarios)
   - [Asignar revisor a un artículo](#asignar-revisor-a-un-artículo)
6. [Customizar y crear agentes](#customizar-y-crear-agentes)
7. [Base documental RAG](#base-documental-rag)
8. [Referencia de API](#referencia-de-api)
9. [Configuración](#configuración)
10. [Estructura de carpetas](#estructura-de-carpetas)
11. [Tests y evaluación](#tests-y-evaluación)
12. [Desarrollo asistido por agentes (Claude Code)](#desarrollo-asistido-por-agentes-claude-code)
    - [Guía interactiva para colaboradores](#guía-interactiva-para-colaboradores)
    - [graphify (grafo de conocimiento del código)](#graphify-grafo-de-conocimiento-del-código)
13. [Spec-Driven Development (SDD)](#spec-driven-development-sdd)

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend API | Python 3.12 · FastAPI · Uvicorn |
| Orquestación de agentes | LangGraph (`StateGraph`) construido desde un `GraphSpec` declarado en `template.yaml` |
| Base de datos | SQLite (dev) · PostgreSQL (prod) · SQLAlchemy async · migraciones con Alembic |
| Vector DB / RAG | Qdrant · una colección por proyecto (`p_<proyecto>__<bucket>`) |
| LLM por defecto | **Anthropic (Claude)** — [SPEC-023](docs/specs/SPEC-023-claude-default-engine.md) / [ADR-0009](docs/adr/0009-claude-default-agentic-engine.md) |
| LLM local | Ollama (`llama3.2`, `gemma2`, `qwen3.5`, …) |
| LLM compatible | OpenAI API / Azure / Groq / vLLM / LM Studio |
| Embeddings | Proveedor independiente del de generación (`EMBED_PROVIDER`): Ollama `nomic-embed-text` u OpenAI |
| Frontend | React 18 · Vite · Zustand · React Flow (`@xyflow/react`) |
| Auth | JWT HS256 · bcrypt · rate limit y bloqueo de login |
| Tiempo real | Server-Sent Events con ticket de un solo uso · bus en memoria o Redis (`REDIS_ENABLED`) |
| Observabilidad | Traza por paso en `agent_run_steps` · Prometheus (`/metrics`) · OpenTelemetry opcional |
| Evaluación | Harness EDD propio (`backend/evals/`) con gate de regresión en CI |

---

## Instalación local

### Requisitos previos

- Python 3.12+
- Node.js 20+
- [Qdrant](https://qdrant.tech/) binario o Docker
- Un proveedor de modelos: una **clave de Anthropic** (motor por defecto) o
  [Ollama](https://ollama.com/) en local
- Para el flujo de desarrollo: [GitHub CLI](https://cli.github.com/) autenticado y
  [Claude Code](https://claude.com/claude-code)

### 1. Clonar y preparar el backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install --require-hashes -r requirements.txt
```

> Las dependencias van con lock y hashes: los rangos se editan en `requirements.in`
> y `requirements.txt` se recompila con `pip-compile` (ver `CLAUDE.md`). No edites
> `requirements.txt` a mano.

### 2. Configurar variables de entorno

Copia el archivo de ejemplo y edítalo:

```bash
cp .env.example .env.local
```

Variables mínimas para desarrollo (rutas relativas a `backend/`, que es desde donde
arranca el servidor):

```env
DATABASE_URL=sqlite+aiosqlite:///./data/dev.db
SECRET_KEY=<genera con: python -c "import secrets; print(secrets.token_hex(32))">
DEBUG=true
ENABLE_DEV_SEED=true            # crea admin@admin y los usuarios de prueba
ENABLE_DEV_ROLE_PROMOTION=true

QDRANT_URL=http://localhost:6333
```

Elige **un** proveedor de generación:

```env
# Anthropic — el motor por defecto del repositorio
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...     # nunca en config.yaml: ese fichero está versionado

# Ollama — en local, sin coste
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b         # modelo de respaldo para agentes sin modelo propio

# OpenAI o compatible
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
# OPENAI_BASE_URL=               # vacío para OpenAI; rellenar para Azure / Groq / vLLM
```

Los **embeddings** del RAG van aparte, porque Anthropic no ofrece API de embeddings:
`EMBED_PROVIDER` (`ollama` u `openai`; vacío = Ollama salvo que generes con OpenAI) y
`OLLAMA_EMBED_MODEL=nomic-embed-text`. La dimensión del índice se deriva del modelo
activo; `RAG_VECTOR_SIZE` solo manda para modelos que la plataforma no conoce.

> Sin `ANTHROPIC_API_KEY` y con el proveedor por defecto, el pipeline falla en el
> primer agente que llama al modelo («ANTHROPIC_API_KEY no está configurada»). Para
> trabajar en local, `dev-local.cmd` ya fija `LLM_PROVIDER=ollama`.

### 3. Descargar modelos Ollama (si usas Ollama)

Estos son los modelos de Ollama que declaran los perfiles de AlejandrIA
(`backend/projects/alejandria-magazine/agents/*.agent.md`):

```bash
ollama pull nomic-embed-text   # embeddings (obligatorio para RAG)
ollama pull gemma2:2b          # investigador
ollama pull llama3.2:3b        # redactor · formateador
ollama pull llama3.2:1b        # revisor · síntesis del investigador sin fuentes
```

> El modelo de cada agente se puede cambiar en **Agentes** o en el nodo del Flow
> Designer; el del nodo manda sobre el perfil. **Modelos que razonan** (`qwen3.5`,
> `olmo-3`): la plataforma les pide `think: false`, porque con el `num_ctx` fijo del
> pipeline gastaban el contexto pensando y devolvían respuestas vacías. `qwen3.5`
> lo respeta; `olmo-3` no, y puede fallar con un error que lo explica.

### 4. Arrancar Qdrant

```bash
# Desde la raíz del proyecto (./storage se crea automáticamente aquí)
.\qdrant\qdrant.exe            # Windows
./qdrant/qdrant                # Linux / macOS
```

### 5. Arrancar el backend

```bash
cd backend
# Con las variables del .env.local exportadas manualmente, o usando dev-local.cmd
uvicorn app.main:app --reload --port 8000
```

### 6. Arrancar el frontend

```bash
cd frontend
npm install
npm run dev
```

### Arranque unificado (Windows)

Desde la raíz del proyecto, el script `dev-local.cmd` levanta Qdrant, el backend y el frontend en ventanas separadas (en Linux o macOS, `dev-local.sh`):

```bat
dev-local.cmd
```

Además fija para el backend `DATABASE_URL` (SQLite en `backend/data/dev.db`),
`DEBUG`, `ENABLE_DEV_SEED` y, **si no los tienes ya definidos**,
`LLM_PROVIDER=ollama` y `OLLAMA_MODEL`. Para usar Claude en local, define
`LLM_PROVIDER=anthropic` y `ANTHROPIC_API_KEY` en tu entorno antes de lanzarlo.

Con la siembra de desarrollo activa, entra con `admin@admin` / `admin123`.

### Documentación (VitePress)

La web de `docs/` **no** la levanta `dev-local`: necesita sus propias dependencias y
se arranca a mano cuando hace falta.

```bash
cd docs
npm install     # solo la primera vez
npm run dev     # http://localhost:5174
```

### Puertos por defecto

| Servicio | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 (en Docker Compose, http://localhost:8080) |
| Swagger UI | http://localhost:8000/docs |
| Qdrant Dashboard | http://localhost:6333/dashboard |
| Ollama | http://localhost:11434 |

### Arranque con Docker Compose

```bash
docker compose up --build
```

Levanta Postgres, Qdrant, Ollama, Redis, backend y frontend.

### Esquema de base de datos

El arranque aplica las migraciones de Alembic (`upgrade head`). Para trabajar el
esquema a mano, desde `backend/`:

```bash
alembic current                            # revisión aplicada
alembic revision --autogenerate -m "..."   # nueva migración desde los modelos
alembic upgrade head
```

**Nunca cambies el esquema con SQL a mano**, y revisa siempre lo que genera
`--autogenerate`: hay un ciclo de claves foráneas `users` ↔ `projects` que no sabe
ordenar.

---

## Cómo funciona la plataforma

La plataforma organiza el trabajo en **proyectos**. Cada proyecto tiene:

- Un **tipo de caso de uso** (`alejandria_magazine`, `desarrollo`, `marketing`, `tiqueting`, `diseno`, `custom`)
- Un conjunto de **agentes** creados a partir de perfiles configurables (modelo LLM, temperatura, RAG, prompt template)
- Una **biblioteca documental** propia indexada en Qdrant para dotar a los agentes de contexto
- Un **diseñador de flujos visual** donde se conectan los agentes en el orden deseado

```
Plataforma
├── Proyecto A: AlejandrIA Magazine
│   ├── Agentes: investigador, redactor, revisor, formateador, publicador
│   └── Flujo: investigador → redactor → revisor → formateador → publicador
│
├── Proyecto B: Desarrollo de software
│   ├── Agentes: arquitecto, backend-dev, frontend-dev, qa-tester, code-reviewer
│   └── Flujo: arquitecto → backend-dev → qa-tester → code-reviewer
│
└── Proyecto C: Marketing
    ├── Agentes: estratega, copywriter, seo-specialist
    └── Flujo personalizado
```

### Ciclo de vida de una ejecución

1. El usuario crea un **artefacto** (artículo, ticket, tarea…) en su proyecto.
2. Selecciona una **secuencia de agentes** y lanza la ejecución.
3. La API resuelve y autoriza el **proyecto activo** (cabecera `X-Project-Id`); todo lo que la ejecución lee o escribe queda acotado a él.
4. El **motor** construye el `StateGraph` de LangGraph desde el `GraphSpec` del proyecto (`backend/projects/<slug>/template.yaml`: secuencia y bucles de revisión) y ejecuta cada nodo.
5. Cada agente recibe el estado acumulado y sus **capacidades** (RAG, LLM, formato…), lo enriquece y lo pasa al siguiente. Los modelos se llaman siempre por el dispatcher único `platform/llm.py`.
6. Cada paso deja una **traza** en `agent_run_steps` (modelo, fuentes RAG, tokens, latencia, decisión del revisor) que sirve `GET /api/v1/agents/{id}/explain`.
7. Los eventos se emiten en tiempo real vía **Server-Sent Events (SSE)**.
8. Al terminar, el artefacto se actualiza en la base de datos y queda disponible para revisión humana.

La forma del pipeline **es un dato**: añadir un agente o cambiar el bucle se hace en
`template.yaml`, no en Python, y la plantilla se valida al cargar (capacidad
inexistente, nodo no declarado o perfil que falta fallan al arrancar).

---

## Gestión de proyectos y agentes

### Crear un proyecto

Desde la interfaz, accede a **Proyectos → Nuevo proyecto**. Elige el tipo de caso de uso y asigna un nombre. Al crear el proyecto, se provisionen automáticamente los agentes predefinidos para ese tipo.

### Agregar agentes a un proyecto

Los agentes se gestionan en la sección **Agentes** del proyecto:

- **Agentes integrados** (`is_builtin = true`): preconfigurados por la plataforma. No pueden borrarse, pero sí editarse.
- **Agentes personalizados**: creados por el usuario desde la misma interfaz.

El nombre de un agente debe ser único dentro del proyecto y usar solo letras minúsculas, números, guiones y guiones bajos.

### Diseñar un flujo

En el **Flow Designer**, los agentes del proyecto aparecen como nodos arrastrables. Conecta los nodos en el orden que necesites. Los flujos se guardan y pueden reutilizarse en múltiples ejecuciones.

---

## Proyecto: AlejandrIA Magazine

AlejandrIA Magazine es el proyecto de referencia de la plataforma. Implementa un flujo editorial completo para la producción de artículos de revista científica mediante un swarm de cinco agentes especializados.

### Flujo de redacción de papers

```mermaid
flowchart TD
    START([Inicio]) --> INPUT["📝 Primera ejecución (modal)\nTítulo · Descripción (opcional)\nElegir documentos del RAG o subir uno nuevo"]
    INPUT --> INV

    subgraph INV_BLOCK["Etapa 1 — Investigación"]
        INV["🔍 Investigador"]
        RAG["RAG (Qdrant)\nbucket del agente + biblioteca compartida\nextrae título/autores de cada documento"]
        SYNTH["Síntesis LLM\nmodelo del agente con fuentes\ntope de 1024 tokens"]
        INV --> RAG --> SYNTH
    end

    INV --> RED["✍️ Redactor\nMarkdown · streaming · num_ctx 4096"]
    RED --> REV["🧐 Revisor\nscore 0-100 · coherencia"]

    REV -- "score < 80\n(máx. 3 iteraciones)" --> RED
    REV -- "no coherente" --> HITL{"⏸️ HITL — decisión del usuario\n¿Subir otra fuente o continuar?"}
    HITL -- "Subir documento" --> INV
    HITL -- "Continuar" --> FMT
    REV -- "aprobado y coherente" --> FMT["📐 Formateador\nAPA · IEEE · Vancouver · Chicago · Nature\ncitas + referencias deterministas"]

    FMT --> PUB["📢 Publicador\nGuarda en DB · maquetación tipo paper (paper_html)\nestado PUBLISHED"]
    PUB --> END([Publicado])
```

> **Primera ejecución**: al lanzar el flujo, el usuario indica en el modal el
> **título**, una **descripción/enfoque** opcional y las **fuentes**: puede
> elegir documentos ya cargados en el RAG o subir uno nuevo. Esas fuentes son las
> que usa el Investigador (no hay scraping web).

#### Paso a paso

| Paso | Agente | Modelo por defecto (Anthropic · Ollama) | Qué hace |
|---|---|---|---|
| 1 | **Investigador** | `claude-opus-5` · `gemma2:2b` (sin fuentes en Ollama: `llama3.2:1b`) | Busca contexto en **RAG (Qdrant)**: en su bucket **y en la biblioteca compartida** del proyecto (`__library__`), con re-ranking semántico; los `rag_doc_ids` elegidos en el modal tienen precedencia. Extrae **título y autores** de cada documento (metadatos PDF + heurística de primera página) para construir citas reales. Sintetiza el contexto con LLM (`timeout 600s`, `num_ctx 8192`, tope de **1024 tokens** de salida). **No realiza scraping web ni consulta APIs externas**; sus fuentes son las del RAG. |
| 2 | **Redactor** | `claude-sonnet-5` · `llama3.2:3b` | Recibe el contexto de investigación y genera un borrador académico estructurado en Markdown (Abstract, Introducción, Metodología, Resultados y Discusión), emitido token a token. Incorpora el feedback del Revisor en iteraciones sucesivas. `num_ctx 4096`, `keep_alive 0`. |
| 3 | **Revisor** | `claude-sonnet-5` · `llama3.2:1b` | Evalúa el borrador (score 0-100 + **coherencia**) y lista comentarios. Si `score < 80` y `loop_count < 3`, reenvía al Redactor. Si determina que la redacción **no es coherente**, dispara un **HITL** que pregunta al usuario: *subir otra fuente* (reejecuta la investigación con el nuevo documento) o *continuar* con el borrador actual. `num_ctx 4096`, `keep_alive 0`. |
| 4 | **Formateador** | `claude-haiku-4-5` · `llama3.2:3b` | Reformatea únicamente las citas y la sección de Referencias según el estilo solicitado: **APA**, **IEEE**, **Vancouver**, **Chicago** o **Nature**. Si el resultado es más corto que el 50 % del original, descarta y devuelve el texto original. `num_ctx 4096`, `keep_alive 0`. |
| 5 | **Publicador** | — (no usa LLM) | Escribe `formatted_text` (o `draft_text` si el formateador no se ejecutó) en la base de datos, cambia el estado a `PUBLISHED` y registra `published_at`. Además genera la **maquetación tipo paper** (HTML imprimible, una plantilla por formato de cita) y la guarda en `paper_html`, accesible en `GET /api/v1/articles/{id}/paper`. |

> **Gestión de memoria** (Ollama): cada agente usa `keep_alive=0` para descargar el modelo de la RAM/VRAM al terminar, evitando conflictos de KV-cache entre agentes. `num_ctx` está fijado por agente para controlar el uso de RAM sin sacrificar calidad.
>
> **Modelo de cada paso**: los modelos de la tabla salen del bloque `models:` de cada `.agent.md`. Se resuelven con una cascada (ajustes de la ejecución → `.agent.md` → default del proveedor), así que el modelo elegido en el nodo del Flow Designer manda sobre el perfil. Ver [Elegir el modelo](#elegir-el-modelo-models-frente-a-model).

#### Revisión, bucle automático y decisión humana (HITL)

```
Redactor ──► Revisor ──(score ≥ 80 y coherente)──► Formateador
    ▲           │
    │ score<80  │ no coherente
    │ y loops<3 ▼
    └──────  ⏸️ HITL — pregunta al usuario
                 ├─ Subir documento ─► vuelve al Investigador (nueva fuente)
                 └─ Continuar ───────► Formateador
```

- **Bucle automático**: el contador `loop_count` se incrementa solo cuando el
  Revisor rechaza por `score < 80`; reenvía al Redactor hasta 3 veces y luego
  avanza igualmente para no bloquear el pipeline.
- **HITL (human-in-the-loop)**: si el Revisor considera que la redacción **no es
  coherente** y hay un cliente escuchando (SSE), **pausa** y pregunta al usuario:
  - **Subir documento** → vuelve al **Investigador** para rehacer la investigación
    con la nueva fuente (hasta 3 reintentos; luego continúa automáticamente).
  - **Continuar** → sigue con el borrador actual hacia el Formateador.

  En modo headless (sin oyente) la decisión por defecto es **continuar**. El
  usuario responde vía `POST /api/v1/agents/{article_id}/decision`.

#### Ejecutar el pipeline

**Desde la UI (primera ejecución):**

1. En el **Flow Designer**, pulsa **Ejecutar pipeline**.
2. Indica el **título**, una **descripción / enfoque** (opcional) y las **fuentes
   de información (RAG)**: elige documentos ya cargados o **sube uno nuevo**. En
   *Opciones avanzadas* puedes añadir palabras clave y una estructura.
3. Pulsa **Ejecutar pipeline**. Los eventos aparecen en tiempo real en el panel de
   ejecución; si el Revisor lanza un **HITL**, responde ahí (subir fuente / continuar).

> Para reejecutar sobre un artículo existente, ve a su detalle → **Reejecutar
> pipeline** y selecciona los agentes y el orden.

**Desde la API:**

```bash
curl -X POST http://localhost:8000/api/v1/agents/{article_id}/run \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "flow_sequence": ["investigador", "redactor", "revisor", "formateador", "publicador"]
  }'
```

**Cancelar un pipeline en ejecución:**

```bash
curl -X DELETE http://localhost:8000/api/v1/agents/{article_id}/run \
  -H "Authorization: Bearer <token>"
```

El artículo queda en estado `DRAFT` con el contenido parcial generado hasta el momento.

**Seguimiento SSE en tiempo real:**

`EventSource` no puede enviar la cabecera `Authorization`, así que el JWT no viaja en
la URL: primero se pide un ticket de un solo uso y con él se abre el stream.

```bash
curl -X POST http://localhost:8000/api/v1/agents/{article_id}/stream-ticket \
  -H "Authorization: Bearer <token>"          # → {"ticket": "..."}
```

```
GET /api/v1/agents/{article_id}/stream?ticket=<ticket>
```

Eventos emitidos: `agent_start`, `token`, `log`, `agent_end`, `agent_error`, `await_decision` (HITL), `done`, `done_error`, `cancelled`.

Cuando el Revisor lanza un HITL emite `await_decision` y **pausa**; el usuario
responde con:

```bash
curl -X POST http://localhost:8000/api/v1/agents/{article_id}/decision \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"decision": "add_source"}'   # o "continue"
```

#### Flujos parciales soportados

```
# Solo redactar sin investigación previa:
redactor → revisor → formateador → publicador

# Solo revisar y reformatear un borrador existente:
revisor → formateador → publicador

# Publicar sin revisión (admin / redactor):
  → botón "Publicar borrador" en la UI (sin pipeline)
```

#### Estado del artículo

```
DRAFT ──► IN_REVIEW ──► PUBLISHED
                    ──► REJECTED ──► DRAFT
DRAFT ──────────────────────────► PUBLISHED  (publicación directa admin/redactor)
```

| Estado | Descripción |
|---|---|
| `draft` | Borrador, editable por el autor. El pipeline puede ejecutarse en cualquier momento. |
| `in_review` | Enviado a revisión humana (submit). No editable hasta resolución. |
| `published` | Aprobado y publicado. Visible en la revista pública. |
| `rejected` | Rechazado por el revisor humano. Vuelve a `draft` con comentario. |

#### Estado compartido entre agentes (`AgentState`)

El orquestador (LangGraph `StateGraph`) pasa un estado tipado entre nodos. Cada
ejecución de agente se registra además en la tabla `agent_runs` para trazabilidad.

```python
class AgentState(TypedDict):
    article_id: UUID
    author_id: UUID
    title: str
    keywords: list[str]
    research_data: str        # Contexto sintetizado por el Investigador
    sources: list[dict]       # Fuentes reales (title, authors, year, url, doi)
    draft_text: str           # Borrador del Redactor
    feedback: list[str]       # Comentarios del Revisor (se acumulan)
    approval_score: float     # Puntuación del Revisor (0-100)
    formatted_text: str       # Texto del Formateador (citas + referencias)
    scientific_format: str    # apa | ieee | vancouver | chicago | nature
    published_url: str
    metadata: dict            # Metadatos de publicación (word_count, licencia…)
    flow_sequence: list[str]  # Nodos a ejecutar
    current_step_index: int
    loop_count: int           # Iteraciones del bucle Revisor → Redactor
    agent_settings: dict      # Overrides por agente (modelo, formato, rag_doc_ids…)
    context_description: str  # Enfoque del autor (Investigador + Redactor)
    article_outline: str      # Estructura/esquema impuesto al Redactor
```

---

### Roles y usuarios

| Rol | Permisos clave |
|---|---|
| **admin** | Gestión completa: usuarios, proyectos, agentes, aprobar/rechazar/publicar artículos directamente |
| **redactor** | Crear y editar artículos, ejecutar pipelines, **publicar borradores directamente** sin pasar por revisión |
| **lector** | Solo lectura del proyecto asignado |
| **publico** | Acceso únicamente al endpoint público de la revista (sin autenticación) |

Al arrancar en modo desarrollo, se crean automáticamente los siguientes usuarios por defecto:

> **Requieren flag explícito** (SPEC-015/T1.6). El arranque solo los siembra con
> `DEBUG=true` **y** `ENABLE_DEV_SEED=true`; `dev-local.cmd` ya los pone. Con
> `DEBUG=false` el flag se fuerza a `False` aunque `config.yaml` lo active, así que
> un despliegue de producción nunca crea estas cuentas.
>
> Se **crean si faltan** y no se reescriben: si cambias la contraseña del admin,
> sobrevive al reinicio.

**Admin**:
- Email: `admin@admin`
- Contraseña: `admin123`

**Redactor de Pruebas**:
- Email: `redactor@example.com`
- Contraseña: `redactor123`

**Revisor Académico**:
- Email: `revisor@example.com`
- Contraseña: `revisor123`

> **Publicación directa**: los roles `admin` y `redactor` ven el botón **Publicar borrador** en el panel lateral del artículo. Este botón publica el artículo inmediatamente sin enviarlo a revisión humana.

---

### Asignar revisor a un artículo

El flujo de revisión humana complementa la revisión automática del agente Revisor:

1. El autor redacta el artículo y ejecuta el pipeline hasta que el texto le satisface.
2. El autor pulsa **Enviar a revisión** → el estado pasa a `in_review`.
3. El **admin** accede a **Artículos en revisión** y abre el artículo.
4. Desde el panel de administración, el admin puede:
   - **Aprobar** → el artículo pasa a `published` y aparece en la revista pública.
   - **Rechazar** → el artículo vuelve a `draft` con un comentario de revisión visible para el autor.
5. El autor recibe una **notificación** en la plataforma con el resultado.

> Solo el rol `admin` puede aprobar o rechazar artículos. El agente Revisor realiza una revisión automática de calidad del borrador, pero la decisión editorial final siempre recae en un administrador humano.

---

## Customizar y crear agentes

Cada agente es un **perfil** almacenado en la base de datos. Los campos configurables son:

| Campo | Tipo | Descripción |
|---|---|---|
| `name` / `slug` | string | Identificador único en el proyecto (ej: `mi-revisor`) |
| `models` | mapa | **Modelo por proveedor** (ej: `{anthropic: claude-sonnet-5, ollama: llama3.2:3b}`). Es lo que hace que el agente funcione al cambiar de proveedor |
| `model` | string | Modelo único, **heredado**. Solo se usa si su *namespace* coincide con el proveedor activo |
| `temperature` | float | Creatividad de las respuestas. Se recorta al rango del proveedor activo: **Anthropic acepta 0-1** y rechaza más; OpenAI y Ollama llegan a 2 |
| `prompt_template` | texto | Instrucciones del sistema para el agente |
| `rag_enabled` | bool | Activa la búsqueda en la base documental |
| `rag_collection` | string | Colección Qdrant sobre la que busca |
| `rag_chunk_size` | int 100-4000 | Tamaño de fragmento al indexar documentos |
| `rag_chunk_overlap` | int 0-499 | Solapamiento entre fragmentos |
| `output_language` | string | Idioma de salida (ej: `spanish`, `english`) |
| `scientific_format` | enum | `apa` · `ieee` · `vancouver` · `none` |
| `target_word_count` | int | Extensión objetivo en palabras |

### Elegir el modelo: `models` frente a `model`

El modelo de un agente **depende del proveedor activo** (`LLM_PROVIDER`), así que un
valor único no vale para todos. La resolución sigue esta cascada
([SPEC-023](docs/specs/SPEC-023-claude-default-engine.md) AC3):

1. el `model` que se pase en los ajustes de esa ejecución;
2. `models[<proveedor>]` del `.agent.md`;
3. el `model` heredado, **solo si su namespace coincide** con el proveedor;
4. el modelo por defecto del proveedor.

Por eso un agente propio conviene que declare `models:` con al menos el proveedor
por defecto (`anthropic`):

```yaml
---
name: mi-agente
models:
  anthropic: claude-sonnet-5
  ollama: llama3.2:3b
temperature: 0.7
---
```

Sin el bloque `models:`, un agente cuyo `model:` sea un id de Ollama cae al modelo
por defecto del proveedor activo — lo correcto, pero no necesariamente el modelo que
quieres para ese agente. Lo que **no** ocurre es que se mande un id de Ollama a la
API de Claude: el paso 3 comprueba el namespace.

### La temperatura se resuelve como el modelo

Misma cascada, y por el mismo motivo: es un ajuste por agente que puede venir de
tres sitios.

1. la `temperature` de los ajustes de esa ejecución (donde el backend funde también
   la del perfil en base de datos, que es la que edita la interfaz);
2. la `temperature` del `.agent.md`;
3. nada — y entonces manda el default del proveedor.

Los valores por defecto están escalonados a propósito: el formateador en `0.1` y el
revisor en `0.2` porque tienen que ser consistentes, el redactor en `0.7` porque
tiene que escribir.

### Crear un agente nuevo desde la UI

1. Ve a **Agentes** dentro de tu proyecto.
2. Haz clic en **Nuevo agente**.
3. Rellena nombre (slug), descripción y elige el modelo LLM.
4. Guarda. El agente aparece disponible en el diseñador de flujos.

### Crear un agente desde la API

```bash
curl -X POST http://localhost:8000/api/v1/agents/claude-defs \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "<uuid-del-proyecto>",
    "name": "mi-agente",
    "description": "Agente especializado en resúmenes ejecutivos",
    "model": "llama3.2:1b",
    "temperature": 0.5,
    "rag_enabled": true,
    "rag_collection": "rag_docs",
    "prompt_template": "Eres un experto en síntesis científica. Responde siempre en español.",
    "output_language": "spanish",
    "target_word_count": 800
  }'
```

### Editar un agente existente

```bash
curl -X PUT http://localhost:8000/api/v1/agents/claude-defs/<agent-uuid> \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "{\"temperature\": 0.3, \"target_word_count\": 1200}"
  }'
```

> Los agentes integrados del sistema (investigador, redactor, revisor, etc.) no pueden borrarse, pero sí modificarse.

---

## Base documental RAG

La plataforma incluye una **biblioteca documental** por proyecto. Los agentes con `rag_enabled = true` buscan automáticamente en esta biblioteca cuando ejecutan: en su propio *bucket* y en la biblioteca compartida del proyecto (`__library__`).

### Subir documentos

Formatos admitidos: `.txt`, `.md`, `.pdf` (máx. 10 MB por archivo).

Desde la UI:
1. Accede a **Documentos** en el menú del proyecto (o sube una fuente desde el modal de ejecución del Flow Designer).
2. Arrastra o selecciona el archivo y haz clic en **Subir**.
3. El documento se divide en fragmentos (chunks), se vectoriza con el proveedor de embeddings (`EMBED_PROVIDER`) y se indexa en Qdrant.

Desde la API (el proyecto viaja en la cabecera `X-Project-Id`):

```bash
curl -X POST http://localhost:8000/api/v1/agents/rag/library/upload \
  -H "Authorization: Bearer <token>" \
  -H "X-Project-Id: <uuid-del-proyecto>" \
  -F "file=@mi-paper.pdf"
```

Si la dimensión de los vectores no coincide con la de la colección (por ejemplo, tras
cambiar de modelo de embeddings), la indexación **se corta con 409** en vez de guardar
vectores inservibles.

### Estructura interna

```
Qdrant
└── colección: p_<project_id>__<bucket>   # se deriva, nunca se recibe
    ├── punto UUID (chunk 1)
    │   ├── vector: [N floats]            # N = dimensión del modelo de embeddings activo
    │   └── payload: { doc_id, filename, agent_name, text, doc_title, doc_authors }
    ├── punto UUID (chunk 2)
    └── ...
```

El nombre de la colección lo compone **solo** `platform/project_context.py` a partir
del proyecto y del *bucket* del perfil (`rag_collection`). Así la biblioteca se
comparte dentro del proyecto y un perfil no puede apuntar al espacio de otro. Para
bases anteriores al aislamiento: `python scripts/migrate_rag_namespaces.py --apply`.

---

## Referencia de API

Documentación interactiva completa en **http://localhost:8000/docs**

Las rutas que leen o escriben datos de un proyecto (agentes, documentos, ejecuciones)
esperan la cabecera **`X-Project-Id`**; el frontend la añade sola.

### Autenticación
| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Registro de usuario |
| `POST` | `/api/v1/auth/login` | Login · devuelve JWT (con rate limit y bloqueo tras intentos fallidos) |
| `GET` | `/api/v1/auth/me` | Usuario autenticado actual |
| `GET` | `/api/v1/auth/users` | Listar usuarios (admin) |
| `PUT` | `/api/v1/auth/users/{id}/role` | Cambiar rol de usuario (admin) |
| `PUT` | `/api/v1/auth/users/{id}/project` | Asignar proyecto a usuario (admin) |
| `POST` | `/api/v1/auth/dev/promote-reviewer` | Autopromoción de rol (solo con `ENABLE_DEV_ROLE_PROMOTION`) |

### Proyectos
| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/projects` | Listar proyectos visibles al usuario |
| `POST` | `/api/v1/projects` | Crear proyecto |
| `GET` | `/api/v1/projects/{id}` | Detalle de proyecto |
| `DELETE` | `/api/v1/projects/{id}` | Eliminar proyecto (admin) |
| `GET` | `/api/v1/projects/access/{user_id}` | Proyectos a los que tiene acceso un usuario |
| `POST` / `DELETE` | `/api/v1/projects/access/{user_id}/{project_id}` | Conceder o retirar acceso a un proyecto |

### Artículos
| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/articles` | Listar artículos |
| `POST` | `/api/v1/articles` | Crear borrador |
| `GET` | `/api/v1/articles/{id}` | Obtener artículo |
| `PUT` | `/api/v1/articles/{id}` | Actualizar artículo |
| `POST` | `/api/v1/articles/{id}/submit` | Enviar a revisión |
| `POST` | `/api/v1/articles/{id}/approve` | Aprobar (admin) |
| `POST` | `/api/v1/articles/{id}/reject` | Rechazar (admin) |
| `POST` | `/api/v1/articles/{id}/publish` | **Publicar directamente** (admin / redactor) |

### Agentes
| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/agents/definitions` | Agentes integrados del sistema |
| `GET` | `/api/v1/agents/claude-defs?project_id=` | Perfiles de agentes del proyecto |
| `POST` | `/api/v1/agents/claude-defs` | Crear agente personalizado |
| `PUT` | `/api/v1/agents/claude-defs/{id}` | Editar agente |
| `DELETE` | `/api/v1/agents/claude-defs/{id}` | Eliminar agente (no integrados) |
| `GET` | `/api/v1/agents/models` | Modelos LLM disponibles en Ollama |
| `GET` | `/api/v1/agents/tools` | Catálogo de herramientas de los agentes |
| `POST` | `/api/v1/agents/{article_id}/run` | Lanzar pipeline |
| `DELETE` | `/api/v1/agents/{article_id}/run` | **Cancelar pipeline en ejecución** |
| `POST` | `/api/v1/agents/{article_id}/decision` | Responder a una pausa humana (HITL) |
| `GET` | `/api/v1/agents/{article_id}/runs` | Historial de ejecuciones |
| `GET` | `/api/v1/agents/{article_id}/explain` | Traza por paso: modelo, fuentes, tokens, latencia y decisión del revisor |
| `POST` | `/api/v1/agents/{article_id}/stream-ticket` | Ticket de un solo uso para abrir el SSE |
| `GET` | `/api/v1/agents/{article_id}/stream?ticket=` | Stream SSE en tiempo real |

### RAG / Biblioteca
| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/agents/rag/collections` | Documentos RAG del proyecto activo en el almacén local |
| `GET` | `/api/v1/agents/rag/library` | Listar documentos indexados |
| `POST` | `/api/v1/agents/rag/library/upload` | Subir documento a la biblioteca del proyecto |
| `POST` | `/api/v1/agents/rag/backfill-metadata` | Completar título y autores de documentos ya indexados |
| `DELETE` | `/api/v1/agents/rag/library/{collection}/{doc_id}` | Eliminar documento |
| `POST` | `/api/v1/agents/{agent}/rag/upload` | Subir documento al bucket de un agente |
| `GET` / `DELETE` | `/api/v1/agents/{agent}/rag/documents[/{doc_id}]` | Listar o borrar documentos de un agente |

### Flujos
| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/flows` | Listar flujos guardados |
| `POST` | `/api/v1/flows` | Guardar nuevo flujo |
| `PUT` | `/api/v1/flows/{id}` | Actualizar flujo |
| `DELETE` | `/api/v1/flows/{id}` | Eliminar flujo |

### Revista pública
| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `GET` | `/api/v1/magazine` | Artículos publicados para el slideshow | No |

### Operación y administración
| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` · `/health/ready` | Vida y preparación (base de datos, Qdrant, proveedor) |
| `GET` | `/metrics` | Métricas Prometheus. Sin autenticación ni proyecto: es para el recolector, no para vistas de producto |
| `GET` / `PUT` | `/api/v1/config` | Leer `config.yaml` (usuario autenticado) y editarlo (admin) |
| `GET` | `/api/v1/config/llm-status` | Proveedor activo y si cada uno está configurado, sin exponer claves |
| `GET` | `/api/v1/audit` | Registro de acciones sensibles (admin) |
| `GET` | `/api/v1/notifications` · `POST /{id}/read` | Notificaciones del usuario |
| `POST` | `/api/v1/checkpoints` · `GET /latest` | Autoguardado de los flujos del Flow Designer |

---

## Configuración

La plataforma carga la configuración con la siguiente prioridad (de mayor a menor):

1. **Variables de entorno**
2. **`config.yaml`** (en la raíz o en `backend/`)
3. **Defaults** en `backend/app/core/config.py`

### Variables principales

Los defaults de la tabla son los del código (`config.py`); `config.yaml` puede
cambiarlos (por ejemplo, fija la base SQLite de desarrollo y `mistral:7b` como modelo
de Ollama por defecto).

| Variable | Default | Descripción |
|---|---|---|
| `SECRET_KEY` | — | **Obligatorio en producción.** Clave para firmar JWT. Generar con `secrets.token_hex(32)` |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:password@localhost:5432/alejandria` | URL de base de datos. En local: `sqlite+aiosqlite:///./data/dev.db` |
| `DEBUG` | `false` | Modo debug |
| `ALLOWED_ORIGINS` | `localhost` y `127.0.0.1` en `:5173` y `:5174` | Orígenes CORS permitidos (coma-separados) |
| `LLM_PROVIDER` | `anthropic` | Proveedor de generación: `anthropic`, `ollama` u `openai` |
| `ANTHROPIC_API_KEY` | — | Clave de Anthropic. Solo por entorno: nunca en `config.yaml` |
| `ANTHROPIC_MODEL` | `claude-opus-5` | Modelo de Claude por defecto |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL de Ollama |
| `OLLAMA_MODEL` | `llama3.2:1b` | Modelo de Ollama por defecto |
| `OPENAI_API_KEY` | — | API key de OpenAI (si `LLM_PROVIDER=openai`) |
| `OPENAI_MODEL` | `gpt-4o-mini` | Modelo OpenAI por defecto |
| `OPENAI_BASE_URL` | — | Override para Azure / Groq / vLLM |
| `LLM_MAX_RETRIES` | `3` | Reintentos ante errores transitorios del proveedor (0 los desactiva) |
| `EMBED_PROVIDER` | vacío | Proveedor de embeddings: `ollama` u `openai`. Vacío = OpenAI si generas con OpenAI, Ollama en otro caso |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Modelo de embeddings de Ollama |
| `QDRANT_URL` | `http://localhost:6333` | URL de Qdrant |
| `QDRANT_COLLECTION` | `rag_docs` | *Bucket* RAG por defecto; la colección real se deriva por proyecto |
| `RAG_VECTOR_SIZE` | `768` | Dimensión solo para modelos de embeddings que la plataforma no conoce |
| `AGENT_ENGINE` | `adapters` | `capabilities` inyecta a cada agente sus capacidades; `adapters` usa sus imports. Dan el mismo resultado |
| `REDIS_ENABLED` | `false` | Bus de eventos en Redis, necesario con varios workers |
| `OTEL_ENABLED` | `false` | Exporta spans de OpenTelemetry (`OTEL_EXPORTER_OTLP_ENDPOINT`) |
| `RETENTION_*` | 30–365 días | Ventanas de retención por tabla. Ver [data-retention.md](docs/governance/data-retention.md) |
| `ENABLE_DEV_ROLE_PROMOTION` | `false` | Permite auto-promoción de rol (solo dev) |
| `ENABLE_DEV_SEED` | `false` | Siembra usuarios de demo y contenido de ejemplo. Forzado a `false` si `DEBUG=false` |
| `DEV_ADMIN_PASSWORD` | `admin123` | Contraseña del admin sembrado (solo con `ENABLE_DEV_SEED`) |

---

## Estructura de carpetas

El backend real vive en `backend/app/` (el `app/` de la raíz no es el código de la
aplicación).

```
.
├── dev-local.cmd               # Arranque unificado Windows (Qdrant + backend + frontend + docs)
├── docker-compose.yml          # Stack completo con Docker (Postgres, Qdrant, Ollama, Redis…)
├── CLAUDE.md                   # Arquitectura en una página y reglas del repo
│
├── backend/
│   ├── requirements.in / .txt  # Rangos y lock con hashes
│   ├── config.yaml             # Configuración de desarrollo (sin secretos)
│   ├── alembic/                # Migraciones del esquema
│   ├── projects/
│   │   └── alejandria-magazine/
│   │       ├── template.yaml   # Agentes, capacidades, secuencia y bucles del proyecto
│   │       └── agents/*.agent.md  # Perfiles que se clonan a base de datos
│   ├── evals/
│   │   ├── agent_behavior/     # Harness EDD: datasets, métricas, gate de regresión
│   │   └── model_benchmark/    # Comparación de modelos foundation
│   ├── tests/                  # pytest (conftest.py protege la base de desarrollo)
│   └── app/
│       ├── main.py             # FastAPI app · lifespan · middlewares · routers
│       ├── core/               # config · database · security · rate_limit · stream_auth
│       ├── models/             # ORM SQLAlchemy y DTOs, un módulo por entidad
│       ├── platform/           # El builder, independiente de cualquier proyecto
│       │   ├── engine/         # GraphSpec → StateGraph · enrutado del bucle de revisión
│       │   ├── capabilities/   # registry · binding · rag · tools
│       │   ├── projects/       # Carga y validación de template.yaml
│       │   ├── llm.py          # Dispatcher único Anthropic / Ollama / OpenAI
│       │   ├── explainability.py  # Traza por paso (agent_run_steps)
│       │   ├── project_context.py · project_access.py  # Aislamiento por proyecto
│       │   ├── egress.py       # Única salida a destinos elegidos por usuario o modelo
│       │   └── bus.py          # Eventos SSE y señales entre workers (memoria o Redis)
│       ├── modules/            # agents · articles · ai · auth (dominio, aplicación, adapters)
│       │   └── agents/
│       │       ├── application/use_cases.py  # Orquestador del pipeline
│       │       └── adapters/   # investigador · redactor · revisor · formateador · publicador
│       ├── routers/            # auth · projects · agents · articles · flows · magazine
│       │                       # ai · config · audit · notifications · checkpoints · health
│       └── shared/             # Siembra de agentes · cliente de Qdrant
│
├── frontend/
│   ├── index.html · index.public.html   # Dos builds de Vite: app y revista pública
│   ├── ds/                   # Sistema de diseño: tokens, fuentes, guías y ejemplos visuales
│   └── src/
│       ├── main.jsx            # Registra el proyecto en el builder al arrancar
│       ├── platform/           # Builder: cliente HTTP, stores, Flow Designer, agentes, documentos
│       └── projects/
│           └── alejandria-magazine/  # Artículos, ejecución, revista, maquetación · catalog.jsx
│
├── docs/
│   ├── specs/ · adr/           # Fuente de verdad de la definición (SDD)
│   ├── governance/             # GOVERNANCE, retención de datos, protección de rama…
│   ├── bitacora/               # Una entrada por tarea resuelta
│   ├── onboarding/             # Contenido editable de la guía para colaboradores
│   ├── public/onboarding/      # Guía generada (alejandria-por-dentro.html)
│   └── public/design-system/   # Referencia visual del sistema de diseño (copia sincronizada de tokens)
│
├── scripts/                    # validate_specs · run-task.sh · build_onboarding · sync_design_system_docs · migraciones RAG
├── .claude/                    # Agentes de desarrollo, comandos, skills y hooks
└── qdrant/ · storage/          # Binario de Qdrant y sus datos locales
```

`platform/` no conoce a ningún proyecto concreto: ni el backend nombra agentes en el
motor, ni el frontend importa de `projects/` desde `platform/` (hay tests que lo
comprueban).

---

## Tests y evaluación

Backend, desde `backend/`. Las variables son obligatorias: sin ellas la validación de
configuración aborta al importar.

```bash
DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q
python -m pytest tests/test_auth_rate_limit_lockout.py -v     # un archivo
python -m pytest -k lockout -v                                 # por nombre
```

- La suite no necesita red ni servicios: Qdrant, la base y los proveedores son
  dobles, y cada test fija su propia base SQLite temporal.
- `tests/conftest.py` **aborta la sesión** si la base efectiva apunta a
  `backend/data/` o no es SQLite: los fixtures borran tablas y vaciarían tu base de
  desarrollo. No debilites esa guarda.
- Hay tests estructurales que protegen reglas de arquitectura (capas del frontend,
  aislamiento por proyecto, egress, migraciones frente a modelos, retención de datos).

Frontend, desde `frontend/`: **las dos builds** deben pasar antes de una PR.

```bash
npm run build          # app principal
npm run build:public   # revista pública
```

Evaluación del comportamiento de los agentes, desde `backend/`
([ADR-0006](docs/adr/0006-adopt-evaluation-driven-development.md)):

```bash
python -m evals.agent_behavior.runner --dataset redactor-smoke --mode replay
python -m evals.agent_behavior.gate          # gate de regresión contra thresholds.yaml
```

`replay` reproduce salidas grabadas y **no evalúa al modelo**; solo `live` lo hace. El
gate corre en CI en las PRs que tocan agentes, prompts, el dispatcher o el motor.

---

## Desarrollo asistido por agentes (Claude Code)

Además de los agentes *de producto* (el pipeline editorial), el repositorio
incluye **agentes de desarrollo** en `.claude/` para trabajar el backlog de
hardening de forma asistida.

Hay **dos** agentes de desarrollo, cada uno con su comando:

| Agente | Comando | Qué hace |
|--------|---------|----------|
| [`sdd-sync`](.claude/agents/sdd-sync.md) | `/sdd-sync [--apply]` | Reconcilia las épicas/tareas del GitHub Project con la **fuente de verdad** (specs/ADRs). |
| [`task-runner`](.claude/agents/task-runner.md) | `/resolve-task <#>` | Implementa **una** tarea del backlog de extremo a extremo. |

Las specs, además, **nacen y maduran** con la capa de autoría
[Spec Kit](https://github.com/github/spec-kit) adaptada a este repo
([ADR-0007](docs/adr/0007-adopt-spec-kit-authoring-layer.md)):
`/speckit-specify` (crear SPEC en Draft), `/speckit-clarify` (ambigüedades),
`/speckit-checklist` (calidad de requisitos) y `/speckit-analyze`
(consistencia SPEC↔ADR↔tareas). Detalle:
[docs/governance/speckit-authoring-aids.md](docs/governance/speckit-authoring-aids.md).

### Flujo de funcionamiento (de la spec al merge)

```
/speckit-specify → clarify → checklist → analyze   ← autoría (recomendado en DoR)
        ▼
docs/specs/SPEC-NNN (bloque sdd-sync)          ← fuente de verdad (definición)
        │  /sdd-sync --apply
        ▼
GitHub Project: épica + tareas (issues)        ← estado de ejecución
        │  /resolve-task <#>
        ▼
task-runner: rama feat/… → implementa → pytest/build
        │  bitácora (docs/bitacora) + push + PR a develop (Closes #N)
        ▼
CI (tests · build · specs · secretos) + review + branch protection
        ▼
Merge a develop  →  criterios de aceptación verificados
```

Los dos agentes cubren tramos distintos del ciclo SDD: `sdd-sync` lleva la
**definición** (specs) al backlog; `task-runner` lleva una tarea del backlog a
**código + PR**. El estado de ejecución (open/closed, progreso) vive siempre en
GitHub; los agentes no lo manipulan a mano.

### `sdd-sync` — del spec al backlog

[`.claude/agents/sdd-sync.md`](.claude/agents/sdd-sync.md) reconcilia el backlog
con las especificaciones, **sin tocar el estado de ejecución**:

1. Lee `docs/specs/SPEC-*.md` en estado `Ready`/`In progress`/`Done` y su bloque
   estructurado `sdd-sync` (sección 8 de la spec): épica + tareas con `id`
   estable, `sev`, `depends_on` y `acceptance`.
2. Empareja con los issues `epic`/`task` por un **marcador oculto** del cuerpo
   (no por título): así es idempotente y no duplica.
3. Calcula el diff y lo clasifica: **CREATE · UPDATE · ADOPT** (adopta issues del
   bootstrap añadiéndoles el marcador) **· DRIFT** (huérfanos) **· NO GESTIONADO**.
4. **Dry-run por defecto** (solo imprime el plan); aplica los cambios únicamente
   con `--apply`. Nunca cierra, borra ni reabre issues.

### `task-runner` — implementa una tarea

[`.claude/agents/task-runner.md`](.claude/agents/task-runner.md) resuelve una
tarea a partir de su número de issue:

1. **Lee la tarea** (`gh issue view <N>`): *Problema*, *Definition of Done* y
   *Dependencias* ("Bloqueada por: #X").
2. **Verifica dependencias**: si alguna está abierta, se detiene y avisa.
3. **Carga contexto**: spec/ADR referenciados y archivos implicados.
4. **Implementa** en una rama `feat|fix|sec|docs|chore/…` (nunca en `develop`).
5. **Verifica** (`pytest`, `npm run build`) como parte del DoD.
6. **Escribe la bitácora** datada en [`docs/bitacora/`](docs/bitacora/) (una
   entrada por ejecución exitosa).
7. **Sube la rama y abre la PR** a `develop` con `Closes #<N>`. No mergea la PR ni
   cierra el issue a mano (el `Closes` lo hace al mergear).
8. **Reporta** el cumplimiento de cada punto del DoD, la bitácora y el enlace de PR.

### Guardarraíles y CI (harness)

Refuerzan la gobernanza a dos niveles:

- **Guardarraíles de sesión** ([`.claude/hooks/`](.claude/hooks/), hooks
  `PreToolUse`): bloquean commit/push directo a ramas protegidas, force-push,
  `--no-verify`, `git add -f` de secretos y `rm -rf` catastrófico; piden
  confirmación en operaciones destructivas. Avisan **antes** de actuar.
- **CI** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)): en cada PR a
  `develop` corre tests de backend, build de frontend, validación de specs
  ([`scripts/validate_specs.py`](scripts/validate_specs.py)), auditoría de
  dependencias (`pip-audit` y `npm audit`) y escaneo de secretos (gitleaks). El
  gate de evaluación de agentes ([`edd-gate.yml`](.github/workflows/edd-gate.yml))
  corre solo en las PRs que tocan agentes, prompts, el dispatcher o el motor.

### Usar los agentes desde la terminal

Dentro de una sesión de Claude Code (`claude` en la raíz del repo, o la extensión de
VS Code):

```text
/resolve-task 119        # implementa la tarea #119 (acepta varios números)
/sdd-sync                # plan de reconciliación specs → issues (dry-run)
/sdd-sync --apply        # aplica los cambios al GitHub Project
```

Sin sesión interactiva, desde Git Bash:

```bash
bash scripts/run-task.sh 119
bash scripts/run-task.sh 119 120 121
```

Requisitos: la CLI `claude` y `gh` autenticado con scopes `repo` y `project`
(`gh auth login --scopes project`). Si acabas de instalar `gh`, reinicia VS Code para
que la terminal lo encuentre.

> `/resolve-task` **se detiene si alguna dependencia sigue abierta**, aunque ya esté
> implementada: una tarea terminada cuyo issue no se ha cerrado bloquea a las que
> dependen de ella. Ciérrala por el flujo (PR con su bitácora y `Closes #N`) antes.

### Guía interactiva para colaboradores

[`docs/public/onboarding/alejandria-por-dentro.html`](docs/public/onboarding/alejandria-por-dentro.html)
es una página autocontenida (se abre directamente en el navegador, y la web de docs la
sirve en `/onboarding/alejandria-por-dentro.html`) con:

- el proyecto y el pipeline de agentes;
- la arquitectura explorable, con un recorrido paso a paso de una ejecución;
- las **tareas abiertas en un Gantt sin fechas**, por olas de dependencias o por
  persona, con la ficha de cada tarea y su `/resolve-task N`;
- cómo ejecutar una tarea, añadir tareas o épicas y regenerar la propia página.

No se edita a mano: la genera [`scripts/build_onboarding.py`](scripts/build_onboarding.py).

```bash
python scripts/build_onboarding.py               # estado de los issues desde GitHub
python scripts/build_onboarding.py --sin-github  # usa la copia docs/onboarding/issues.json
```

Tareas, severidad, dependencias y criterios salen de las specs; número y estado de
cada issue, de GitHub; lo editorial (alcance, archivos, «ojo con», reparto) de
[`docs/onboarding/tareas.yaml`](docs/onboarding/tareas.yaml) y la arquitectura de
[`docs/onboarding/arquitectura.yaml`](docs/onboarding/arquitectura.yaml).
Regénerala tras `/sdd-sync --apply` o al mergear PRs que cierran tareas. Detalle en
[`docs/onboarding/README.md`](docs/onboarding/README.md).

### graphify (grafo de conocimiento del código)

Herramienta **de desarrollo** (no es funcionalidad del producto) que convierte el
backend en un grafo de conocimiento navegable: *god nodes*, comunidades y
relaciones entre archivos extraídas por AST. Útil para orientarse en el código y
para que Claude Code responda preguntas de arquitectura con un subgrafo acotado en
lugar de un grep completo. Skill de Claude Code: `/graphify`.

```bash
pip install -r requirements-dev.txt   # instala graphifyy (separado del runtime)

# Construir / actualizar el grafo del backend (solo AST, sin coste de API)
graphify update backend

# Consultar el grafo ya construido
graphify explain "call_llm()" --graph backend/graphify-out/graph.json
graphify path "UserModel" "ArticleModel" --graph backend/graphify-out/graph.json
```

El grafo se genera en `backend/graphify-out/` (`graph.json`, `graph.html`,
`GRAPH_REPORT.md`) y está **ignorado por git** — es un artefacto local por máquina.
Los hooks del guardián de graphify viven en `.claude/settings.local.json` (local,
no versionado) para no afectar a otras máquinas ni al CI. Opcionalmente,
`graphify hook install` añade un hook `post-commit` que reconstruye el grafo tras
cada commit. Web del proyecto: <https://graphify.net>.

---

## Spec-Driven Development (SDD)

El proyecto trabaja con **Spec-Driven Development**: la especificación va *antes*
que el código. Decisión y proceso en
[ADR-0002](docs/adr/0002-adopt-spec-driven-development.md).

### Flujo

```
Idea ─▶ Spec (docs/specs) ─▶ ADR si hay decisión arquitectónica
     ─▶ Bloque sdd-sync en la spec ─▶ /sdd-sync --apply ─▶ Épica + Tareas (GitHub Project)
     ─▶ /resolve-task <#> ─▶ Rama feat/… ─▶ PR contra develop
     ─▶ CI verde + revisión ─▶ Verificación de criterios de aceptación ─▶ Merge
```

La **fuente de verdad** de la definición es `docs/specs` + `docs/adr`; el
**estado de ejecución** vive en el GitHub Project. El agente
[`sdd-sync`](.claude/agents/sdd-sync.md) reconcilia una con otra (ver
[GOVERNANCE §7](docs/governance/GOVERNANCE.md)).

### Cómo añadir una especificación (y crear tareas nuevas)

1. **Crea la spec** con `/speckit-specify "descripción"` (o a mano desde
   [`docs/specs/TEMPLATE.md`](docs/specs/TEMPLATE.md)) como `SPEC-NNN-titulo.md`
   (ID incremental, no se reutiliza). Rellena problema, objetivos, **criterios de
   aceptación** (Given/When/Then) y el resto, y madúrala con `/speckit-clarify`,
   `/speckit-checklist` y `/speckit-analyze`.
2. **Declara épica y tareas** en el bloque `sdd-sync` (sección 8) con `id`
   estables, `sev`, `depends_on` y `acceptance`. Cambia el **Estado** a `Ready`.
3. **Regístrala** en el índice de [`docs/specs/README.md`](docs/specs/README.md) y,
   si hay decisión arquitectónica, añade el **ADR** correspondiente.
4. Abre la PR `docs/…` a `develop`. La CI valida el formato del bloque con
   [`scripts/validate_specs.py`](scripts/validate_specs.py).
5. Tras el merge, ejecuta **`/sdd-sync`** (revisa el plan) y **`/sdd-sync --apply`**
   para crear/actualizar la épica y las tareas en el GitHub Project. Luego
   **`/resolve-task <#>`** por cada tarea, en el orden que marcan sus dependencias.
6. Regenera la [guía para colaboradores](#guía-interactiva-para-colaboradores) para
   que las tareas nuevas aparezcan en ella.

> **Una tarea nueva en una épica que ya existe** no necesita spec nueva: añádela al
> bloque `sdd-sync` de su spec (y, si hace falta, su criterio en la sección 3), valida,
> PR y `/sdd-sync --apply`. **Nunca crees issues de épica o tarea a mano**: sin el
> marcador oculto que pone `/sdd-sync` quedan «no gestionados», y un duplicado bloquea
> la sincronización.

#### En un área existente vs. un área nueva

Las áreas registradas son: `area/security`, `area/infra`, `area/backend`,
`area/observability`, `area/governance`, `area/ux`, `area/evaluation`, `area/qa`.

- **Área existente (p. ej. Observabilidad `area/observability` E5, o UX/diseño
  `area/ux` E7 — ver [SPEC-003](docs/specs/SPEC-003-ux-design-system-accessibility.md)):**
  basta con los pasos de arriba; en el bloque `sdd-sync` pon el `epic.area`
  correspondiente y un `epic.id` de esa área o uno nuevo si abres otra épica.
- **Área nueva (la que no esté en la lista de arriba):** primero **da de alta el
  área** (es un cambio de gobernanza, no solo una spec). Tomando `area/<nueva>`:
  1. Añade la label `area/<nueva>` en [`scripts/seed_github_project.py`](scripts/seed_github_project.py) (lista `LABELS`)
     y créala en GitHub (`gh label create area/<nueva>`).
  2. Añádela al conjunto `ALLOWED_AREAS` de
     [`scripts/validate_specs.py`](scripts/validate_specs.py) para que la CI la acepte.
  3. Refléjala en [GOVERNANCE §7](docs/governance/GOVERNANCE.md) y en el
     [backlog](docs/backlog/).
  4. Ya puedes crear la spec con `epic.area: area/<nueva>` y un `epic.id` nuevo, y
     seguir el flujo normal (`/sdd-sync --apply` → `/resolve-task`).

### Documentación

| Documento | Contenido |
|-----------|-----------|
| [docs/specs/](docs/specs/) | Especificaciones + plantilla y ciclo de vida (Draft→Ready→Done). |
| [docs/adr/](docs/adr/) | Architecture Decision Records. |
| [docs/governance/GOVERNANCE.md](docs/governance/GOVERNANCE.md) | Roles, **Definition of Ready/Done**, política de revisión, fuente de verdad. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Flujo de contribución (SDD) y estándares. |
| [SECURITY.md](SECURITY.md) | Política y modelo de amenazas. |
| [docs/backlog/](docs/backlog/) | Épicas y tareas de hardening (overview). |
| [docs/bitacora/](docs/bitacora/) | Bitácora de tareas resueltas (una entrada por ejecución). |
| [docs/governance/data-retention.md](docs/governance/data-retention.md) | Qué se guarda y cuánto tiempo (`RETENTION_*`). |
| [docs/onboarding/](docs/onboarding/) | Guía interactiva para colaboradores y cómo regenerarla. |
| [frontend/ds/](frontend/ds/README.md) | Sistema de diseño: marca, fuentes, color, [tokens](frontend/ds/tokens.md), [accesibilidad](frontend/ds/ACCESSIBILITY.md) y ejemplos visuales (`preview/`, `ui_kits/`). Los valores reales están en [`colors_and_type.css`](frontend/ds/colors_and_type.css). |
| [docs/public/design-system/](docs/public/design-system/index.html) | **Referencia visual del sistema de diseño**: una página por secciones (color, tipografía, componentes, accesibilidad, tema oscuro…). Pública en <https://onpremialabs.github.io/swarm-platform-builder/design-system/> (workflow `ds-pages.yml`) y en la web de docs en `/design-system/`. Ver [docs/guide/design-system.md](docs/guide/design-system.md). |

### Backlog y GitHub Project

El **bootstrap inicial** del GitHub Project (jerárquico: campo `Epic`,
sub-issues épica→tareas, DoD y dependencias) se hace una sola vez:

```bash
# Bootstrap del Project con todo el backlog (requiere gh con scope project)
python scripts/seed_github_project.py

# Eliminar el Project y sus issues (destructivo)
python scripts/delete_github_project.py --yes
```

`seed_github_project.py` es un **script de un solo uso**, no un sync incremental
(y con `--force` recrea el Project de forma destructiva). A partir del bootstrap, las
épicas/tareas se mantienen al día desde las specs con **`/sdd-sync --apply`** (agente
[`sdd-sync`](.claude/agents/sdd-sync.md)).

El backlog vive hoy en **dos tableros** de GitHub Projects, ambos con un campo `Epic`:

| Tablero | Épicas |
|---|---|
| [Hardening & Platform Backlog](https://github.com/users/onpremialabs/projects/7) | E1–E12: bootstrap y hardening |
| [Roadmap: calidad, evaluación y vistas agénticas](https://github.com/users/onpremialabs/projects/8) | E13 y de E14 en adelante: selección de modelos, QA, evaluación con deepeval, portada, trazabilidad, entrada de referencia, fine-tune |

> `/sdd-sync --apply` decide el tablero por la épica del issue y rellena su campo
> `Epic`. La tabla que asigna épicas a tableros vive en
> [`.claude/agents/sdd-sync.md`](.claude/agents/sdd-sync.md) (paso 4.3); una épica
> nueva va al roadmap salvo que esa tabla diga otra cosa.

En cada tablero: **View ▸ Group by ▸ Epic**, o una vista **Roadmap**. Para
implementar una tarea: `/resolve-task <#>` o `bash scripts/run-task.sh <#issue>`.

---

## Licencia

Consulta el archivo [LICENSE](LICENSE) para más información.

