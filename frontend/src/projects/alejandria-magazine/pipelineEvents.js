// Interpretación de los eventos de cierre del pipeline que comparten las pantallas de
// ejecución en vivo (ExecutionPage y TraceabilityPage). Funciones puras, sin React ni
// i18n, para poder probarlas con `node --test` (SPEC-034/AC13).
//
// Contrato del backend (`Orchestrator.run`): cuando el Investigador se abstiene se emite
// `abstained` (agent, message, verified_sources, min_sources) y luego
// `done` con `outcome: "abstained"` y los mismos datos. Una ejecución normal emite `done`
// a secas. Una pantalla que ignore `outcome` presenta como completada una ejecución que
// se detuvo: ese fue el defecto de TraceabilityPage tras T22.12.

export const OUTCOME_ABSTAINED = 'abstained';

/** ¿Es el aviso de abstención del Investigador? */
export const isAbstainedEvent = (data) => data?.type === 'abstained';

/** ¿Es el cierre `done` de una ejecución detenida por abstención? */
export const isAbstainedDone = (data) => data?.type === 'done' && data?.outcome === OUTCOME_ABSTAINED;

/** Datos del aviso destacado («El Investigador se abstuvo», k/N, mensaje). */
export const abstentionNotice = (data) => ({
  kind: 'abstained',
  message: data?.message,
  verified: data?.verified_sources,
  min: data?.min_sources,
});

/** Los pasos que seguían «esperando» no se van a ejecutar en esta pasada: «No ejecutado». */
export const settleUnrunSteps = (steps) => steps.map((step) => (
  step.status === 'waiting' ? { ...step, status: 'not_run' } : step
));
