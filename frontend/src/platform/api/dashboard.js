import api from './client';

export const dashboardApi = {
  /**
   * Métricas de portada del proyecto activo (SPEC-028 / T16.2 / AC1).
   *
   * El cliente NO pasa el project_id: el interceptor de api/client.js lo
   * adjunta automáticamente como X-Project-Id.  El backend lo valida a través
   * de get_project_context, garantizando el aislamiento por proyecto (AC6).
   *
   * Magnitudes devueltas (AC2 — qué cuenta cada campo):
   *   tokens_in / tokens_out : suma de tokens de entrada/salida de agent_run_steps
   *   latency_p50_ms         : mediana de latencia de paso de agente (no HTTP)
   *   articles_analyzed      : artículos distintos con al menos un paso en 7 días
   *   agent_runs_total       : ejecuciones en agent_runs ligadas al proyecto
   *   anomalies              : 4 condiciones enumeradas (0 = «comprobado, ningún caso»)
   *   articles               : estado real del pipeline por artículo (desde agent_run_steps)
   */
  getSummary: () => api.get('/dashboard/summary').then(r => r.data),
};
