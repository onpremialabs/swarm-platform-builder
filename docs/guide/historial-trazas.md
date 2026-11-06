# Historial de trazas por artículo

La consulta histórica se encuentra en `/dashboard/articles/:id/observability`. Se abre desde Trazabilidad > Trazas y desde el detalle del artículo. La ejecución en vivo continúa en `/dashboard/execution/:articleId` cuando se inicia desde el diseñador con su secuencia. Los enlaces antiguos sin secuencia redirigen al historial.

## Datos y selección

`GET /api/v1/agents/{article_id}/history` enumera las ejecuciones conservadas, más recientes primero. `GET /api/v1/agents/{article_id}/history/{execution_id}` devuelve los pasos, fuentes agregadas e integridad de una ejecución. Ambos reutilizan el control de acceso del artículo (autor o administrador, y comprobación del proyecto activo).

El identificador estable de consulta es el UUID del primer paso conservado del grupo. La agrupación mantiene el criterio existente del motor: step_index vuelve a cero. La tabla del proyecto añade trace_id para abrir exactamente la pasada seleccionada, sin depender de una numeración limitada a siete días.

## Interfaz

- Resumen: resultado técnico, fallos recuperados, tokens, tiempo acumulado, recorrido y decisiones.
- Trazas por agente: todos los intentos, modelo, entrada, salida guardada, errores y JSON.
- Logs: cronología derivada de los pasos persistidos, búsqueda, filtros y páginas de 20 registros. No representa eventos SSE archivados.
- Métricas: consumo y tiempo por agente, incluidos reintentos.
- Fuentes: documentos y fragmentos identificados por el RAG. Recuperar una fuente no demuestra que se haya citado; no se dispone del texto completo de cada fragmento en estas filas.
- Integridad: comprobación de hashes de los pasos de la ejecución seleccionada y límites de dicha comprobación.

Exportar JSONL descarga localmente un manifiesto y los pasos de la ejecución seleccionada, incluidos sus hashes. No publica ni sube datos. No es el formato de eventos JSONL de la otra copia del proyecto.

El estado técnico se deriva del último intento conservado de cada paso (agente, índice, iteración). Los errores recuperados permanecen visibles y contabilizados; una ejecución completada no implica aprobación editorial. El historial refleja los pasos guardados y no es un monitor vivo: un pipeline interrumpido sin marcador final puede requerir consultar la ejecución activa. La duración suma tiempos de intentos, no tiempo de reloj. No se modifican credenciales, umbrales ni el flujo del pipeline.

## Tecnologías y validación

Se utilizan React, React Router, Axios, Zustand, Lucide, ReactMarkdown, CSS, FastAPI y SQLAlchemy ya presentes; no se añaden dependencias ni migraciones.

Pruebas: aislamiento entre ejecuciones y artículos, permisos por autor/proyecto, historial vacío, conservación de fallos recuperados y regresión de explicabilidad/resumen. Verificación en navegador con el artículo de Cristiano, filtro de errores, detalle, métricas, fuentes, integridad, descarga y regreso a Trazabilidad.
