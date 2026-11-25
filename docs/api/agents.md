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
