// Nodo de agente del lienzo — pieza **del builder** (SPEC-013 / T8.6 / AC7).
//
// Aquí vivía el catálogo de los cinco agentes de AlejandrIA, con sus iconos, sus
// colores y sus descripciones. Es el equivalente en el frontend de lo que T8.3
// quitó del motor: la pieza reutilizable conociendo por su nombre a los agentes
// de un proyecto concreto. Con eso, el lienzo de otro proyecto pintaba todos sus
// nodos grises y sin descripción, y no había forma de arreglarlo sin editar este
// fichero.
//
// Ahora los metadatos llegan en `data` (los pone quien construye el nodo, desde
// el catálogo de su proyecto) y aquí solo queda el fallback genérico.
import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Bot, Zap } from 'lucide-react';
import { useTranslation } from '../../i18n';

export const AgentNode = memo(({ data, selected }) => {
  const { t } = useTranslation();
  const meta = {
    Icon:  data.icon  || Bot,
    color: data.color || 'var(--neutral-60)',
    label: data.label || data.agentId,
    desc:  data.desc  || '',
  };

  return (
    <div className={`agent-node${selected ? ' selected' : ''}`}
      style={{ borderColor: selected ? meta.color : undefined }}>
      <Handle type="target" position={Position.Left}
        style={{ background: meta.color, border: `2px solid ${meta.color}` }} />

      <div className="agent-node-header">
        <span className="agent-node-icon"
          style={{ width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center',
                   background: `${meta.color}18`, borderRadius: 4 }}>
          <meta.Icon size={13} style={{ color: meta.color }} strokeWidth={1.5} />
        </span>
        <span className="agent-node-name">{meta.label}</span>
      </div>
      <div className="agent-node-desc">{meta.desc}</div>
      <div className="agent-node-badge"
        style={{ background: `${meta.color}20`, color: meta.color }}>
        {t('node.agentBadge')}
      </div>
      {(data.model || (data.ragEnabled && data.ownRag)) && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
          {data.model && (
            <div className="agent-node-badge" style={{ marginTop: 0, background: 'var(--blue-05)', color: 'var(--blue-60)' }}>
              {data.model}
            </div>
          )}
          {data.ragEnabled && data.ownRag && (
            <div className="agent-node-badge" style={{ marginTop: 0, background: 'var(--green-05)', color: 'var(--green-60)' }}>
              RAG
            </div>
          )}
        </div>
      )}

      <Handle type="source" position={Position.Right}
        style={{ background: meta.color, border: `2px solid ${meta.color}` }} />
    </div>
  );
});

export const ConditionNode = memo(({ data, selected }) => {
  const { t } = useTranslation();
  return (
  <div className={`condition-node${selected ? ' selected' : ''}`}>
    <Handle type="target" position={Position.Left} />
    <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 4 }}>
      <Zap size={16} style={{ color: 'var(--warning)' }} strokeWidth={1.5} />
    </div>
    <div className="condition-node-label">{data.label || t('node.condition')}</div>
    {data.expression && (
      <div className="condition-node-expr">{data.expression}</div>
    )}
    <Handle type="source" position={Position.Right} id="true"
      style={{ top: '30%', background: 'var(--agent-format)', border: '2px solid var(--agent-format)' }} />
    <Handle type="source" position={Position.Right} id="false"
      style={{ top: '70%', background: 'var(--red-60)', border: '2px solid var(--red-60)' }} />
  </div>
  );
});

export const nodeTypes = {
  agent: AgentNode,
  condition: ConditionNode,
};

