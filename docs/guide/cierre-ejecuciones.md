# Cierre de intentos de agentes

Cada fila en agent_runs es un intento de agente. Los estados completed, failed, cancelled e interrupted son finales y llevan finished_at. No constituyen una cola ni ejecutan trabajo. Se conserva el historial para auditar; el estado del enjambre solo considera running sin finished_at.

## Funcionamiento

- El wrapper de los agentes protege tanto la preparación como la llamada al agente. CancelledError se maneja explícitamente, cierra el intento y registra su traza cancelada antes de propagarse.
- El cierre tiene tres intentos de escritura. La actualización es condicional: un resultado terminal ya guardado no se sobreescribe por un cierre posterior. Si la base falla temporalmente, se conserva el resultado final en memoria para volver a persistirlo cuando termine la tarea y vuelva la base.
- Cada instancia del backend posee un identificador y un bloqueo de archivo del sistema operativo. Su identidad se registra en input_payload._runtime_owner, sin migración ni dependencia nueva. El bloqueo se mantiene abierto mientras la instancia esté viva; el sistema lo libera incluso si el proceso termina forzosamente.
- Al arrancar y cada 15 segundos, se concilian registros abiertos cuyos dueños de este equipo ya no existen o cuyas tareas locales terminaron. Se guarda interrupted y finished_at, o el resultado final pendiente si sigue disponible. No se decide la muerte de un proceso solo por la duración del agente.
- En el apagado normal se solicita la cancelación de pipelines locales, se espera hasta 10 segundos y se concilian registros de tareas terminadas. Si una tarea aún no termina, su bloqueo se conserva hasta que salga el proceso, para no declarar muerta una tarea viva.

Los archivos de bloqueo se guardan en backend/data/runtime-owners y se retiran al liberar normalmente el dueño o conciliar sus registros abandonados. No son tareas ni una cola. No se mata Ollama ni los servicios de otros procesos.

## Alcance

La comprobación automática es local al equipo y a su directorio de bloqueos. Un registro antiguo sin metadatos de dueño, de otro servidor o con identidad inválida no se cierra por suposición. Los cuatro registros heredados identificados en esta sesión ya se cerraron tras comprobar su origen. La gestión entre hosts requiere un mecanismo compartido de propiedad y queda fuera de esta modificación local.

Un cierre forzado puede impedir guardar la traza parcial en el momento exacto del corte. La conciliación cierra el registro del intento y conserva los datos existentes; no inventa salidas ni modifica hashes anteriores. La fecha de una conciliación es la fecha de cierre administrativo, no la hora exacta de interrupción. Si la base está inaccesible, no se puede garantizar la persistencia hasta que vuelva a estar disponible.

## Archivos

- backend/app/platform/run_lifecycle.py: propiedad de instancias, bloqueos del sistema, conciliación y apagado.
- backend/app/modules/agents/application/use_cases.py: cierre idempotente con reintentos, propiedad de cada intento y manejo de cancelación/preparación.
- backend/app/main.py: inicio y apagado del monitor de conciliación.
- backend/tests/test_run_lifecycle.py: éxito, error, cancelación, error de preparación, recuperación de escritura, dueño vivo/muerto, salida forzada de un proceso de prueba y apagado.

Se utilizan asyncio, bibliotecas estándar de Python (msvcrt en Windows / fcntl en Unix) y SQLAlchemy ya presente. No se añadieron paquetes ni tablas.
