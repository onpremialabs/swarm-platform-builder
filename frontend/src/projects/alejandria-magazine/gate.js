import { agentMeta } from './catalog';

// Compuerta de publicación (SPEC-032, ADR-0011): textos y ayudas para mostrarla.
//
// El backend responde con códigos estables (`detail.code`); aquí se traducen a algo
// que una persona pueda actuar. Si el backend añade un código y aquí no se traduce,
// un test estructural lo detecta (`test_frontend_gate.py`).

export const CRITERION_LABELS = {
  reference_existence: 'Las referencias existen y coinciden',
  reference_structure: 'Las referencias están completas',
  retractions: 'Sin referencias retractadas',
  placeholders: 'Sin marcadores de posición',
  imrad_structure: 'Estructura IMRaD',
};

export const CRITERION_STATUS = {
  passed: { label: 'Superado', cls: 'badge-approved' },
  failed: { label: 'No supera', cls: 'badge-error' },
  not_verified: { label: 'No verificado', cls: 'badge-pending' },
  not_implemented: { label: 'Pendiente de fase', cls: 'badge-draft' },
};

// Un criterio `failed` o `not_verified` bloquea; `not_implemented` no (AC5).
export const BLOCKING = new Set(['failed', 'not_verified']);

/** Nombre de un agente: sale del catálogo del proyecto, que es la única lista (T8.6). */
export function agentLabel(agentId) {
  return agentMeta(agentId).label || agentId;
}

// Códigos de 409/403 de `approve`, `publish` y `responsible-author`.
export const GATE_ERROR_MESSAGES = {
  no_responsible_author: 'Declara un autor responsable antes de aprobar.',
  no_gate_report: 'Aún no hay informe de la compuerta: evalúa el texto antes de aprobar.',
  text_changed: 'El texto cambió desde la última evaluación: reevalúa la compuerta.',
  gate_blockers: 'La compuerta tiene bloqueantes: corrígelos y vuelve a evaluar.',
  not_reviewer: 'Solo el administrador o el revisor asignado puede aprobar.',
  owner_cannot_approve: 'Quien lanzó el pipeline no puede aprobar su propio artículo.',
  review_missing: 'El texto no ha pasado por una revisión: ejecútalo con el Revisor.',
  review_not_verified: 'El Revisor no pudo producir una revisión válida: vuelve a ejecutarlo.',
  score_below_threshold: 'La revisión no alcanza la puntuación mínima.',
  not_coherent: 'El Revisor considera el texto incoherente.',
  no_approval: 'Falta la aprobación humana.',
  approval_stale: 'La aprobación es de una versión anterior del texto.',
};

/**
 * Texto de un error de la API de artículos: acepta `detail` como cadena o como
 * `{code, message}` y prefiere la explicación accionable de este módulo.
 */
export function describeApiError(err, fallback = 'No se pudo completar la acción') {
  const detail = err?.response?.data?.detail;
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  return GATE_ERROR_MESSAGES[detail.code] || detail.message || fallback;
}

/** Resumen de una línea de la evidencia de un criterio. */
export function evidenceLines(criterion) {
  const out = [];
  for (const e of criterion?.evidence || []) {
    if (e.reason) out.push(`${e.title ? `«${e.title}»: ` : ''}${e.reason}`);
    else if (e.missing) out.push(`«${e.title}»: falta ${e.missing.join(', ')}`);
    else if (e.pattern) out.push(`${e.pattern} (línea ${e.line}, columna ${e.column})`);
    else if (e.problem) out.push(`${e.section}: ${e.problem}`);
  }
  return out;
}

// Fases del plan del framework (SPEC-032) y qué dato falta para cada criterio que aún
// no se comprueba: se muestra para que «sin comprobar» no parezca «superado».
export const PENDING_REASONS = {
  V01: 'Necesita la ficha del estudio (tipo, guía y perfil) que aún no se genera.',
  V05: 'Necesita el protocolo sellado y el registro de desviaciones.',
  V06: 'Necesita los resultados primarios declarados en el protocolo.',
  V07: 'Necesita el registro de búsqueda (bases, fechas y cadenas).',
  V08: 'Necesita el diagrama de flujo de selección de estudios.',
  V12: 'Necesita el registro de uso de agentes para componer la declaración de IA.',
  V13: 'Necesita comprobar autores y autor responsable contra el registro.',
  V14: 'Necesita contribuciones CRediT, conflictos de interés y financiamiento.',
  V16: 'Necesita la declaración de datos y código y los metadatos FAIR.',
};

export const ACTION_LABELS = {
  rerun_agent: (agent) => `Reejecutar desde ${agentLabel(agent)}`,
  provide_doi: () => 'Aportar DOI',
  edit_text: () => 'Editar el texto',
};

/** Líneas de lo que se comprobó en un criterio (`summary` del informe; ausente en informes antiguos). */
export function summaryLines(criterion) {
  const s = criterion?.summary;
  if (!s) return [];
  switch (s.code) {
    case 'reference_existence':
      return [`${s.ok} de ${s.total} referencias resueltas en Crossref/OpenAlex.`];
    case 'reference_structure':
      return [`${s.ok} de ${s.total} referencias con todos sus datos.`];
    case 'retractions': {
      const out = [];
      if (s.retracted) out.push(`${s.retracted} referencia(s) retractada(s) o retirada(s).`);
      if (s.concern) out.push(`${s.concern} con expresión de preocupación.`);
      if (s.unchecked) out.push(`${s.unchecked} sin poder comprobar en Crossref.`);
      return out.length ? out : ['Ninguna referencia retractada ni con expresión de preocupación.'];
    }
    case 'placeholders':
      return s.found ? [`${s.found} marcadores de posición en el texto.`] : ['Ningún marcador de posición en el texto.'];
    case 'imrad_structure':
      return s.problems?.length
        ? []
        : [`Secciones comprobadas, en orden: ${(s.sections || []).join(', ')}.`];
    default:
      return [];
  }
}

/** Qué hacer a continuación según el informe; `null` si no hay nada que proponer. */
export function nextStep(data) {
  const report = data?.report;
  if (!report) return { code: 'evaluate', text: 'Aún no hay informe: evalúa la compuerta.', action: { action: 'reevaluate' } };
  if (!data.current) {
    return { code: 'stale', text: 'El texto cambió desde la última evaluación: reevalúa.', action: { action: 'reevaluate' } };
  }
  const blocking = (report.criteria?.criteria || []).filter((c) => BLOCKING.has(c.status));
  if (blocking.length === 0) {
    return { code: 'approve', text: 'La compuerta no tiene bloqueantes: queda la aprobación humana.', action: null };
  }
  const first = blocking.find((c) => c.actions?.length) || blocking[0];
  return {
    code: 'fix',
    text: `Falta corregir: ${CRITERION_LABELS[first.criterion] || first.criterion}.`,
    action: first.actions?.[0] ? { ...first.actions[0], criterion: first.criterion } : null,
  };
}

/**
 * Etapas del manuscrito hasta «Publicado» y en qué punto está cada una (FW §3).
 * Los agentes salen de `agentIds` (el catálogo del proyecto); la compuerta, la
 * aprobación y la publicación se derivan del artículo y del informe. Estados:
 * `done`, `current`, `failed` o `pending`.
 */
export function stageStates({ article, runs, gateData, agentIds }) {
  const latest = {};
  for (const r of [...(runs || [])].sort((a, b) => String(a.started_at).localeCompare(String(b.started_at)))) {
    latest[r.agent_name] = r;
  }
  const stages = agentIds.map((id) => {
    const run = latest[id];
    const state = !run ? 'pending'
      : run.status === 'completed' ? 'done'
      : run.status === 'failed' ? 'failed'
      : 'current';
    return { id, label: agentLabel(id), state };
  });
  const review = gateData?.report?.criteria?.review;
  if (review && typeof review.approval_score === 'number') {
    const rev = stages.find((s) => s.id === 'revisor');
    if (rev) rev.detail = `${review.approval_score}/100`;
  }

  const report = gateData?.report;
  const gateState = !report ? 'pending'
    : !gateData.current ? 'current'
    : report.criteria?.passed ? 'done' : 'failed';
  const published = article?.status === 'published';
  const approved = published || article?.status === 'approved';
  stages.push({ id: 'gate', label: 'Compuerta', state: gateState });
  stages.push({
    id: 'approval', label: 'Aprobación humana',
    state: approved ? 'done' : gateState === 'done' ? 'current' : 'pending',
  });
  stages.push({ id: 'published', label: 'Publicado', state: published ? 'done' : 'pending' });
  return stages;
}
