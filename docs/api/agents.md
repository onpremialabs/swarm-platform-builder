# Agentes API

## Listar agentes de un proyecto

```bash
curl "http://localhost:8000/api/v1/agents/claude-defs?project_id=<uuid>" \
  -H "Authorization: Bearer <token>"
```

## Crear agente

```bash
curl -X POST http://localhost:8000/api/v1/agents/claude-defs \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "<uuid>",
    "name": "sintetizador",
    "description": "Crea resúmenes ejecutivos de artículos científicos",
    "model": "llama3.2:1b",
    "temperature": 0.4,
    "rag_enabled": true,
    "rag_collection": "rag_docs",
    "output_language": "spanish",
    "target_word_count": 600
  }'
```

## Lanzar pipeline

```bash
curl -X POST http://localhost:8000/api/v1/agents/{article_id}/run \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "flow_sequence": ["investigador", "redactor", "revisor", "formateador", "publicador"],
    "keywords": ["inteligencia artificial", "revisión sistemática"],
    "context_description": "Artículo para revista de tecnología aplicada",
    "agent_settings": {
      "redactor": {
        "model": "mistral",
        "temperature": 0.7,
        "output_language": "spanish",
        "target_word_count": 2000
      },
      "formateador": {
        "scientific_format": "apa"
      }
    }
  }'
```

### Presupuesto de salida del Redactor y borradores truncados (SPEC-036/AC10)

`agent_settings.redactor` acepta dos límites, resueltos con la misma cascada que el modelo y
la temperatura (ajustes de la ejecución → `redactor.agent.md` → defecto) y acotados por la
ventana del modelo activo:

| Clave | Qué es | Defecto |
|---|---|---|
| `num_ctx` | Ventana de contexto (solo Ollama) | `4096` |
| `max_output_tokens` | Tope de tokens de salida (`num_predict` en Ollama, `max_tokens` en Anthropic/OpenAI) | el del proveedor |

Un valor no numérico o menor de 256 se ignora con aviso en tiempo de ejecución, y en el perfil
`.agent.md` **impide cargar el proyecto** (error de plantilla con el nombre del campo).

`agent_settings.revisor` acepta `num_ctx` y `timeout_seconds` (SPEC-036/T24.11), con la misma
cascada. Son el **mínimo**: el Revisor dimensiona la ventana por el borrador (texto + rúbrica +
margen de salida) y el tiempo por su tamaño, con la ventana del modelo como techo. Si el prompt no
cabe en esa ventana **no se envía recortado**: el resultado es `review_status: not_verified` con el
motivo. Un tiempo agotado se reintenta una sola vez con el doble de límite (nunca con el mismo);
`decision.review_budget` en la traza (`GET /agents/{id}/explain`) dice ventana, límite, reintentos y
segundos consumidos. `timeout_seconds` menor de 5 impide cargar el perfil.

**Decisión humana sin respuesta (SPEC-036/T24.8/AC9).** Si nadie responde a `await_decision`
(sin oyente, sin canal o tras 900 s) el desenlace es `no_response`, **no** «continue»: el SSE
`decision_resolved` lleva `decision: "no_response"` y `timed_out: true`, y el bucle sigue por umbral
y vueltas hasta `requires_human_review`. `POST /agents/{id}/decision` solo acepta `continue` y
`add_source`; el usuario y el instante van en `decision_resolved` (`by`, `at`) y en la traza
(`decision.hitl`: `origin` `person`/`no_response`/`no_channel`/`source_retry_limit`, `outcome`, `by`, `at`;
`hitl_outcome` pasa a `no_response` cuando nadie decidió).

**Ventana del Redactor por el prompt (SPEC-036/T24.12/AC13).** `num_ctx` del Redactor es un
**mínimo**, no un tope: antes de generar se estima el prompt (3 caracteres por token, por exceso) y
se le suma el margen de salida (`max_output_tokens` si está fijado; si no, 2 tokens por palabra de
`target_word_count`, mínimo 2048; sin objetivo, 4096). La ventana pedida es ese total redondeado a
múltiplos de 1024, nunca menor que `num_ctx` y nunca mayor que la ventana del modelo. Así un prompt
de ~16 000 tokens con `num_ctx: 16384` se envía de una vez con una ventana mayor, en lugar de
cortarse con `length` y gastar un reintento. Si el prompt no cabe ni en la ventana del modelo **no se
envía**: el Redactor quita fragmentos citables enteros por prioridad de sección (primero los sin
sección, luego el sobrante de la sección con más fragmentos, y solo al final la cobertura de una
sección, de la de menor prioridad) y, si ni así cabe, el paso **falla antes de generar** con el
motivo. La traza (`GET /agents/{article_id}/explain`, columna `decision`) lleva `prompt_budget`:
`num_ctx` pedido y configurado, tokens del prompt, margen, ventana del modelo, `outcome`
(`ok` / `trimmed` / `does_not_fit`), `fragments_total`, `fragments_removed`, `removed` (id, sección y
motivo de cada uno) y `sections_lost`. El reintento por truncado de abajo queda para cortes que no se
podían prever.

Si el borrador sale **truncado** (motivo de parada `length`/`max_tokens` del proveedor o, sin
motivo, faltan secciones del IMRaD o el texto acaba sin cierre de frase), el Redactor reintenta
**una vez** con el doble de presupuesto (sin pasar de la ventana del modelo). Si persiste, el paso
**falla** con el motivo y no llega al Revisor. Cada intento cortado queda en la columna `decision`
de la traza (`GET /agents/{article_id}/explain`), bajo la clave `truncation`.

## Escuchar eventos SSE en tiempo real

```bash
curl -N http://localhost:8000/api/v1/agents/{article_id}/stream \
  -H "Authorization: Bearer <token>"
```

Cada evento tiene el formato:

```
data: {"agent": "redactor", "event": "chunk", "content": "..."}
data: {"agent": "redactor", "event": "done", "tokens": 1240}
```

## Historial de ejecuciones

```bash
curl http://localhost:8000/api/v1/agents/{article_id}/runs \
  -H "Authorization: Bearer <token>"
```
