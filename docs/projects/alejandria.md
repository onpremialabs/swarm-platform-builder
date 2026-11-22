# AlejandrIA Magazine

AlejandrIA Magazine es el proyecto de referencia de la plataforma. Implementa un flujo editorial completo para la producción de artículos de revista científica mediante un swarm de cinco agentes especializados.

## Agentes del swarm

| Agente | Modelo sugerido | Responsabilidad |
|---|---|---|
| **Investigador** | `llama3.2:1b` | Busca contexto en Qdrant y lo cruza con la biblioteca del proyecto: solo los documentos con DOI verificado entran en `sources`/Referencias; sin al menos `research.min_sources` (3 por defecto) se abstiene (SPEC-034). |
| **Redactor** | `llama3.2` / `mistral` | Genera el borrador académico en Markdown. Incorpora feedback del Revisor en iteraciones. |
| **Revisor** | `llama3.2` | Evalúa el borrador con puntuación 0-100 y genera comentarios. Si score < 80, reenvía al Redactor (máx. 3 ciclos). |
| **Formateador** | `llama3.2:1b` | Reformatea citas y referencias: APA, IEEE o Vancouver. |
| **Publicador** | — | Guarda el texto final en DB, cambia estado a `PUBLISHED`, registra fecha. |

## Formatos científicos disponibles

| Código | Nombre |
|---|---|
| `apa` | American Psychological Association |
| `ieee` | Institute of Electrical and Electronics Engineers |
| `vancouver` | Vancouver (biomédico) |
| `none` | Sin formato específico |

## Primeros pasos

1. Inicia sesión con tu cuenta `redactor` o `admin`.
2. Accede al proyecto **AlejandrIA Magazine** en el selector de proyectos.
3. Crea un artículo en **Artículos → Nuevo artículo**.
4. Sigue el [flujo de redacción](/projects/alejandria-flow).
