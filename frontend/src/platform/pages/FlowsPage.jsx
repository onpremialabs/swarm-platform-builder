import React, { useEffect, useState } from 'react';
import { AsyncState, EmptyState } from '../components/ui/states';
import { useNavigate } from 'react-router-dom';
import { Zap, Play, Pencil, Trash2, Plus, GitBranch, Clock } from 'lucide-react';
import { useFlowStore } from '../store/flowStore';
import { agentMeta, flowAutoPublishes } from '../agentCatalog';
import toast from 'react-hot-toast';

// Etiquetas de la lista, juntas para extraerlas cuando llegue el i18n (SPEC-041).
// Publicar exige compuerta determinista y aprobación humana (SPEC-032): ningún flujo
// publica solo, así que la etiqueta no puede decir «Auto-publica» (SPEC-037 AC8).
const FLOW_LABELS = {
  withPublisher: 'Pasa por compuerta y aprobación humana',
  withoutPublisher: 'No publica: queda en borrador',
};

export default function FlowsPage() {
  const navigate = useNavigate();
  const { flows, fetchFlows, loadFlow, deleteFlow, newFlow, isLoading, error } = useFlowStore();

  useEffect(() => { fetchFlows(); }, []);

  const handleEdit = async (flow) => {
    await loadFlow(flow.id);
    navigate('/dashboard/flow-designer');
  };

  const handleDelete = async (id) => {
    if (!confirm('¿Eliminar este flujo?')) return;
    try {
      await deleteFlow(id);
      toast.success('Flujo eliminado');
    } catch { toast.error('Error al eliminar'); }
  };

  const handleNew = () => {
    newFlow();
    navigate('/dashboard/flow-designer');
  };

  // Qué agente publica lo dice el proyecto (T8.6).
  const hasPublicador = (flow) => flowAutoPublishes(flow.flow_sequence);

  return (
    <div className="page-body">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-6)' }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>Flujos</h2>
          <p style={{ fontSize: 'var(--font-size-sm)' }}>Pipelines guardados</p>
        </div>
        <button className="btn btn-primary" onClick={handleNew}>
          <Plus size={15} /> Nuevo flujo
        </button>
      </div>

      <AsyncState
        loading={isLoading}
        error={error}
        isEmpty={flows.length === 0}
        onRetry={fetchFlows}
        loadingLabel="Cargando flujos…"
        empty={(
          <EmptyState
            icon={<GitBranch size={28} />}
            title="Sin flujos guardados"
            description="Crea tu primer pipeline en el Flow Designer."
            action={<button className="btn btn-primary" onClick={handleNew}><Plus size={14} /> Crear flujo</button>}
          />
        )}
      >
        {(
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          {flows.map(flow => (
            <div key={flow.id} className="card" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)', padding: 'var(--space-4) var(--space-5)' }}>
              <div style={{ width: 40, height: 40, background: 'var(--brand-primary-light)', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <Zap size={20} style={{ color: 'var(--brand-primary)' }} />
              </div>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 'var(--font-size-base)', marginBottom: 4 }}>{flow.name}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                  {(flow.flow_sequence || []).map((agentId, i) => {
                    const meta = agentMeta(agentId);
                    return (
                      <React.Fragment key={i}>
                        <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 3 }}>
                          {meta?.emoji} {meta?.label || agentId}
                        </span>
                        {i < flow.flow_sequence.length - 1 && (
                          <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>→</span>
                        )}
                      </React.Fragment>
                    );
                  })}
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                {hasPublicador(flow)
                  ? <span className="badge badge-pending">{FLOW_LABELS.withPublisher}</span>
                  : <span className="badge badge-draft">{FLOW_LABELS.withoutPublisher}</span>
                }
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Clock size={11} />
                  {new Date(flow.updated_at || flow.created_at).toLocaleDateString('es-ES')}
                </div>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button className="btn btn-ghost btn-sm btn-icon" title="Editar" onClick={() => handleEdit(flow)}>
                    <Pencil size={14} />
                  </button>
                  <button className="btn btn-ghost btn-sm btn-icon" title="Eliminar" onClick={() => handleDelete(flow.id)}>
                    <Trash2 size={14} style={{ color: 'var(--status-error)' }} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
        )}
      </AsyncState>
    </div>
  );
}
