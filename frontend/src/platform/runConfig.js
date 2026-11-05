// Parámetros de ejecución, lado cliente (SPEC-030 / T18.3, T18.5 / AC3, AC6).
//
// **La autoridad es el backend**: `backend/app/platform/run_config.py` declara el
// tope de las notas y qué modos existen, y el endpoint de ejecución los valida —un
// modo no disponible se rechaza con 422 y su motivo—. Lo de aquí es la afordancia:
// que el contador avance mientras escribes y que la opción no disponible se vea
// como tal antes de pulsar «Ejecutar».
//
// Están duplicados a sabiendas, y conviene saber qué pasa si divergen: la
// interfaz enseñaría un tope o una opción que el servidor no acepta, y el error
// llegaría al ejecutar en vez de al escribir. Molesto, no peligroso — lo contrario
// (que el cliente decida qué es válido) sí lo sería.

/** Tope de las notas del enjambre. Espejo de `MAX_SWARM_NOTES`. */
export const MAX_SWARM_NOTES = 2000;

/** Modos de aprendizaje del formato. Espejo de `FORMAT_MODES`. */
export const FORMAT_MODES = {
  rag: {
    label: 'RAG',
    available: true,
    detail: 'El formato se aprende recuperando el documento de referencia.',
  },
  finetune: {
    label: 'Fine-tune',
    available: false,
    detail: 'Pendiente de decidir en SPEC-031; no se puede seleccionar todavía.',
  },
};

export const DEFAULT_FORMAT_MODE = 'rag';
