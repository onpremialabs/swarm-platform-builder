// Arista del lienzo que se puede borrar (BUG-003).
//
// Antes la única vía era la tecla Supr sobre una arista seleccionada con un clic
// en una línea de 1 px, y `deleteKeyCode="Delete"` además dejó sin efecto la tecla
// Retroceso, que en muchos portátiles es la única «borrar». Aquí la arista tiene un
// área de clic ancha y, una vez seleccionada, un botón visible para eliminarla.
import React from 'react';
import { BaseEdge, EdgeLabelRenderer, getBezierPath, useReactFlow } from '@xyflow/react';
import { X } from 'lucide-react';
import { useTranslation } from '../../i18n';

export function DeletableEdge({
  id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition,
  markerEnd, style, selected, interactionWidth, ariaLabel,
}) {
  const { t } = useTranslation();
  const { deleteElements } = useReactFlow();
  const [path, labelX, labelY] = getBezierPath({
    sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition,
  });

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        interactionWidth={interactionWidth ?? 28}
        style={selected ? { ...style, strokeWidth: 3 } : style}
      />
      {selected && (
        <EdgeLabelRenderer>
          <button
            type="button"
            className="flow-edge-delete nodrag nopan"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
            aria-label={ariaLabel ? t('edge.deleteNamed', { name: ariaLabel }) : t('edge.delete')}
            title={t('edge.delete')}
            onClick={() => deleteElements({ edges: [{ id }] })}
          >
            <X size={12} aria-hidden="true" />
          </button>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

// `default` es el tipo de las aristas sin `type`, que son todas las ya guardadas.
export const edgeTypes = { default: DeletableEdge };
