import React from 'react';
import { CheckCircle, Circle, AlertCircle, Loader } from 'lucide-react';
import { useT } from '../i18n/useT';

const ICON = {
  done: <CheckCircle size={14} aria-hidden="true" />,
  current: <Loader size={14} aria-hidden="true" />,
  failed: <AlertCircle size={14} aria-hidden="true" />,
  pending: <Circle size={14} aria-hidden="true" />,
};
const COLOR = {
  done: 'var(--success)', current: 'var(--warning)', failed: 'var(--error)', pending: 'var(--text-muted)',
};

/**
 * Línea de etapas del manuscrito hasta «Publicado»: de un vistazo, dónde está y
 * qué falta. El estado se deriva fuera (`stageStates`); aquí solo se pinta.
 */
export default function PipelineStages({ stages }) {
  const { t } = useT();
  return (
    <ol aria-label={t('stages.aria')} style={{
      listStyle: 'none', display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)',
      padding: 0, margin: '0 0 var(--space-4)', fontSize: 'var(--font-size-xs)',
    }}>
      {stages.map((s) => (
        <li key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 4, color: COLOR[s.state] }}
          aria-label={t('stages.itemAria', { label: s.label, state: t(`stages.state.${s.state}`) })}>
          {ICON[s.state]}
          <span>{s.label}{s.detail ? ` (${s.detail})` : ''}</span>
        </li>
      ))}
    </ol>
  );
}
