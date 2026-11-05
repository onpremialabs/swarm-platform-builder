import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { runTarget } from '../runTarget';
import { DEFAULT_FORMAT_MODE, FORMAT_MODES, MAX_SWARM_NOTES } from '../runConfig';
import Modal from '../components/ui/Modal';
import { EmptyState } from '../components/ui/states';
import {
  ReactFlow, Background, Controls, MiniMap,
  addEdge, useNodesState, useEdgesState, Panel,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useNavigate, useLocation } from 'react-router-dom';
import { Pencil, Plus, Save, Play, Trash2, GitBranch, Upload, AlertTriangle } from 'lucide-react';
import { nodeTypes } from '../components/flow/AgentNode';
import { edgeTypes } from '../components/flow/DeletableEdge';
import { agentIds, agentMeta, hasOwnRag, listAgents, ragOwner } from '../agentCatalog';
import { AgentCreateModal, AgentEditorModal } from '../components/agents/AgentEditorModal';
import { useFlowStore } from '../store/flowStore';
import {
  ERROR, NO_RULES, blocking, effectiveSequence, issueFromError, validateConnection, validateFlow,
} from '../flowValidation';
import { useProjectStore } from '../store/projectStore';
import { agentsApi } from '../api/agents';
import { flowsApi } from '../api/flows';
import toast from 'react-hot-toast';

//: Agentes de serie: los del proyecto activo, más el orquestador, que no es
//: un nodo del pipeline (T8.6).
const builtinIds = () => new Set([...agentIds(), 'orquestador']);

let nodeId = 100;
const newId = () => `node_${++nodeId}`;

export default function FlowDesignerPage() {
  const navigate = useNavigate();
  const location = useLocation();
  // When navigating from ArticleDetailPage, an existing article can be passed
  const existingArticleId = location.state?.existingArticleId || null;
  const existingArticleTitle = location.state?.existingArticleTitle || '';
  const {
    draftNodes, draftEdges, draftName,
    setDraftNodes, setDraftEdges, setDraftName,
    saveFlow, saveDraftLocally, loadLocalDraft, clearLocalDraft,
    activeFlow,
  } = useFlowStore();
  // El objetivo de la ejecución lo aporta el proyecto activo (T8.6): el
  // builder no sabe cómo se llama lo que produce el pipeline.
  const target = runTarget();
  const { activeProject } = useProjectStore();

  const [nodes, setNodes, onNodesChange] = useNodesState(draftNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(draftEdges);
  const [flowName, setFlowName] = React.useState(draftName);
  const [saving, setSaving] = React.useState(false);
  const [showRunModal, setShowRunModal] = React.useState(false);
  const [runTitle, setRunTitle] = React.useState(existingArticleTitle);
  const [runKeywords, setRunKeywords] = React.useState([]);
  const [runKeywordInput, setRunKeywordInput] = React.useState('');
  const [runDescription, setRunDescription] = React.useState('');
  const [runOutline, setRunOutline] = React.useState('');
  // Parámetros de esta ejecución (SPEC-030 / T18.3, T18.5).
  const [runNotes, setRunNotes] = React.useState('');
  const [runFormatMode, setRunFormatMode] = React.useState(DEFAULT_FORMAT_MODE);
  const [showAdvanced, setShowAdvanced] = React.useState(false);
  // RAG source selection for the run
  const [runDocs, setRunDocs] = React.useState([]);
  const [selectedDocIds, setSelectedDocIds] = React.useState([]);
  const [loadingDocs, setLoadingDocs] = React.useState(false);
  const [uploadingDoc, setUploadingDoc] = React.useState(false);
  const runFileRef = useRef(null);
  const [models, setModels] = React.useState(['llama3.2:1b']);
  const [paletteAgents, setPaletteAgents] = React.useState([]);
  const [editAgent, setEditAgent] = React.useState(null);
  const [showNewAgent, setShowNewAgent] = React.useState(false);
  const reactFlowWrapper = useRef(null);
  const [rfInstance, setRfInstance] = React.useState(null);
  // Reglas de dependencia entre agentes: las declara el proyecto, no el lienzo.
  const [rules, setRules] = React.useState(NO_RULES);

  const issues = useMemo(() => validateFlow(nodes, edges, rules), [nodes, edges, rules]);
  const errors = useMemo(() => blocking(issues), [issues]);

  // Marca en el lienzo lo que falla: el nodo y la arista implicados, no solo un texto.
  const displayNodes = useMemo(() => {
    const marks = new Map();
    issues.forEach((i) => i.nodes.forEach((n) => {
      if (marks.get(n) !== ERROR) marks.set(n, i.severity);
    }));
    return nodes.map((n) => (marks.has(n.id) ? { ...n, className: `flow-issue-${marks.get(n.id)}` } : n));
  }, [nodes, issues]);

  const displayEdges = useMemo(() => {
    const marks = new Map();
    issues.forEach((i) => i.edges.forEach((e) => {
      if (marks.get(e) !== ERROR) marks.set(e, i.severity);
    }));
    const names = new Map(nodes.map((n) => [n.id, n.data?.label || n.data?.agentId || n.id]));
    return edges.map((e) => {
      const withLabel = { ...e, ariaLabel: `conexión de ${names.get(e.source)} a ${names.get(e.target)}` };
      return marks.has(e.id)
        ? { ...withLabel, className: `flow-issue-${marks.get(e.id)}`, style: { ...e.style, stroke: `var(--${marks.get(e.id) === ERROR ? 'error' : 'warning'})` } }
        : withLabel;
    });
  }, [nodes, edges, issues]);

  const buildPaletteAgent = useCallback((agent) => {
    const meta = agentMeta(agent.slug) || agentMeta(agent.id) || {};
    return {
      id: agent.slug || agent.id,
      slug: agent.slug || agent.id,
      // Real DB UUID — needed for save/delete API calls (the slug is the node id).
      profileId: agent.id,
      content: agent.content,
      model: agent.model,
      temperature: agent.temperature,
      prompt_template: agent.prompt_template,
      rag_enabled: agent.rag_enabled,
      rag_collection: agent.rag_collection,
      scientific_format: agent.scientific_format,
      output_language: agent.output_language,
      target_word_count: agent.target_word_count,
      emoji: meta.emoji || '🤖',
      color: meta.color || 'var(--neutral-60)',
      label: meta.label || agent.name || agent.slug || agent.id,
      desc: meta.desc || `Perfil ${agent.slug || agent.id}`,
      icon: meta.icon,
    };
  }, []);

  const loadPaletteAgents = useCallback(async () => {
    try {
      const projectId = activeProject?.id;
      if (!projectId) {
        setPaletteAgents(listAgents());
        return;
      }
      const defs = await agentsApi.getClaudeDefs(projectId);
      setPaletteAgents(defs.map(buildPaletteAgent));
    } catch {
      setPaletteAgents(listAgents());
    }
  }, [buildPaletteAgent, activeProject?.id]);

  // Auto-checkpoint every 30s
  useEffect(() => {
    const timer = setInterval(() => {
      setDraftNodes(nodes);
      setDraftEdges(edges);
      setDraftName(flowName);
      saveDraftLocally();
    }, 30000);
    return () => clearInterval(timer);
  }, [nodes, edges, flowName]);

  // Check for local draft on mount
  useEffect(() => {
    if (!activeFlow) {
      const draft = loadLocalDraft();
      if (draft && draft.draftNodes?.length > 0) {
        toast((t) => (
          <span style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            Tienes un borrador sin guardar
            <button className="btn btn-primary btn-sm" onClick={() => {
              setNodes(draft.draftNodes);
              setEdges(draft.draftEdges);
              setFlowName(draft.draftName);
              toast.dismiss(t.id);
            }}>Restaurar</button>
            <button className="btn btn-ghost btn-sm" onClick={() => {
              clearLocalDraft(); toast.dismiss(t.id);
            }}>Descartar</button>
          </span>
        ), { duration: 10000 });
      }
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    loadPaletteAgents();
    // mejor-esfuerzo: sin reglas el lienzo valida lo estructural y el backend, el resto.
    flowsApi.rules().then((r) => { if (mounted) setRules(r); }).catch(() => {});
    // mejor-esfuerzo: el desplegable de modelos; el lienzo funciona sin él.
    agentsApi.getModels().then((response) => {
      if (mounted) {
        setModels(response.models || ['llama3.2:1b']);
      }
    }).catch(() => {});
    return () => {
      mounted = false;
    };
  }, [loadPaletteAgents]);

  useEffect(() => {
    if (paletteAgents.length === 0) {
      return;
    }

    setNodes((current) => current.map((node) => {
      if (node.type !== 'agent') {
        return node;
      }

      const paletteAgent = paletteAgents.find((agent) => agent.id === node.data?.agentId);
      if (!paletteAgent) {
        return node;
      }

      return {
        ...node,
        data: {
          ...node.data,
          label: paletteAgent.label,
          emoji: paletteAgent.emoji,
          color: paletteAgent.color,
          desc: paletteAgent.desc,
          icon: paletteAgent.icon ?? agentMeta(node.data?.agentId)?.icon,
          ownRag: hasOwnRag(node.data?.agentId),
          model: paletteAgent.model,
          ragEnabled: paletteAgent.rag_enabled,
          scientificFormat: paletteAgent.scientific_format,
          outputLanguage: paletteAgent.output_language,
          targetWordCount: paletteAgent.target_word_count,
        },
      };
    }));
  }, [paletteAgents, setNodes]);

  // Rechaza ya en el arrastre: el puerto no se ilumina como destino válido.
  const isValidConnection = useCallback((connection) => !validateConnection(connection), []);

  const onConnect = useCallback((params) => {
    const problem = validateConnection(params);
    if (problem) {
      toast.error(problem.message);
      return;
    }
    setEdges(eds => addEdge({ ...params, animated: true, style: { stroke: 'var(--brand-primary)' } }, eds));
  }, []);

  const onDragOver = useCallback((e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    const agentId = e.dataTransfer.getData('application/agentId');
    if (!agentId) return;

    const bounds = reactFlowWrapper.current.getBoundingClientRect();
    const position = rfInstance.screenToFlowPosition({
      x: e.clientX - bounds.left,
      y: e.clientY - bounds.top,
    });

    const agent = paletteAgents.find((entry) => entry.id === agentId);

    const node = {
      id: newId(),
      type: 'agent',
      position,
      data: {
        agentId,
        label: agent?.label || agentMeta(agentId)?.label || agentId,
        emoji: agent?.emoji ?? agentMeta(agentId)?.emoji,
        color: agent?.color ?? agentMeta(agentId)?.color,
        desc: agent?.desc ?? agentMeta(agentId)?.desc,
        // El icono y la insignia de RAG los pinta el nodo con lo que reciba: es
        // el precio de que `AgentNode` ya no conozca a los agentes de nadie.
        icon: agent?.icon ?? agentMeta(agentId)?.icon,
        ownRag: hasOwnRag(agentId),
        model: agent?.model,
        ragEnabled: agent?.rag_enabled,
        scientificFormat: agent?.scientific_format,
        outputLanguage: agent?.output_language,
        targetWordCount: agent?.target_word_count,
      },
    };

    setNodes(nds => [...nds, node]);
  }, [paletteAgents, rfInstance]);

  const handleSave = async () => {
    if (errors.length > 0) {
      toast.error(errors[0].message);
      return;
    }
    setSaving(true);
    setDraftNodes(nodes);
    setDraftEdges(edges);
    setDraftName(flowName);
    try {
      await saveFlow();
      clearLocalDraft();
      toast.success('Flujo guardado');
    } catch (err) {
      toast.error(issueFromError(err) || 'Error al guardar');
    } finally {
      setSaving(false);
    }
  };

  // Flatten the /rag/library response ({collections:[{name,documents:[...]}]}) into a doc list
  const flattenLibrary = (data) =>
    (data?.collections || []).flatMap(c => (c.documents || []).map(d => ({ ...d, collection: c.name })));

  // Load available RAG documents when the run modal opens
  useEffect(() => {
    if (!showRunModal) return;
    setLoadingDocs(true);
    agentsApi.getLibraryDocs()
      .then(data => setRunDocs(flattenLibrary(data)))
      .catch(() => setRunDocs([]))
      .finally(() => setLoadingDocs(false));
  }, [showRunModal]);

  const handleRunUpload = () => runFileRef.current?.click();

  const onRunFileSelected = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setUploadingDoc(true);
    try {
      // Upload to the investigador bucket so it's available as a source
      // A qué agente pertenecen las fuentes que se suben desde el lienzo lo
      // dice el proyecto: en AlejandrIA es el investigador (T8.6).
      const res = await agentsApi.uploadRagDocument(ragOwner(), file);
      toast.success(
        res?.title
          ? `Añadido: "${res.title}"${res.authors ? ` — ${res.authors}` : ''}`
          : `Documento añadido: ${file.name}`
      );
      const data = await agentsApi.getLibraryDocs();
      setRunDocs(flattenLibrary(data));
      if (res?.doc_id) setSelectedDocIds(ids => [...new Set([...ids, res.doc_id])]);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No se pudo subir el documento');
    } finally {
      setUploadingDoc(false);
    }
  };

  const handleRun = async () => {
    const titleValue = runTitle.trim();
    if (!titleValue && !existingArticleId) { toast.error('Escribe un título para el artículo'); return; }
    if (errors.length > 0) { toast.error(errors[0].message); return; }
    try {
      let articleId;
      if (existingArticleId) {
        // Re-run on existing article; optionally update the title if user changed it
        articleId = existingArticleId;
        if (titleValue && titleValue !== existingArticleTitle) {
          await target.rename(existingArticleId, titleValue);
        }
      } else {
        const creado = await target.create(titleValue);
        articleId = creado.id;
      }
      setShowRunModal(false);
      const agentNodes = nodes.filter(n => n.type === 'agent');
      // En el orden en que se ejecutan: el de las aristas, que es el que se validó.
      const flowSequence = effectiveSequence(nodes, edges);
      // Build per-agent model settings from node data
      const agentSettings = {};
      agentNodes.forEach(n => {
        if (n.data.agentId && n.data.model) {
          agentSettings[n.data.agentId] = {
            model: n.data.model,
            ...(n.data.scientificFormat ? { scientific_format: n.data.scientificFormat } : {}),
            ...(n.data.outputLanguage ? { output_language: n.data.outputLanguage } : {}),
            ...(n.data.targetWordCount ? { target_word_count: n.data.targetWordCount } : {}),
          };
        }
      });
      // Inject selected RAG documents as the Investigador's sources
      if (selectedDocIds.length > 0) {
        const selected = runDocs.filter(d => selectedDocIds.includes(d.doc_id));
        const collection = selected[0]?.collection;
        agentSettings.investigador = {
          ...(agentSettings.investigador || {}),
          rag_doc_ids: selectedDocIds,
          ...(collection ? { rag_collection: collection } : {}),
        };
      }

      // El estado de navegación pasa por `history.pushState`, que lo clona con
      // structured clone: nada de funciones ni componentes. Los nodos llevan su
      // icono (un componente de lucide) en `data.icon`, y mandarlos aquí lanzaba
      // DataCloneError después de haber creado el artículo. La página de
      // ejecución solo necesita la secuencia y los ajustes.
      navigate(`/dashboard/execution/${articleId}`, {
        state: {
          flowSequence,
          agentSettings,
          keywords: runKeywords,
          contextDescription: runDescription,
          articleOutline: runOutline,
          swarmNotes: runNotes,
          formatMode: runFormatMode,
        }
      });
    } catch (err) {
      console.error('Error al iniciar pipeline', err);
      toast.error(issueFromError(err) || err?.response?.data?.detail || 'Error al iniciar pipeline');
    }
  };

  return (
    <div className="flow-designer-layout">
      {/* Agent Palette */}
      <div className="flow-palette">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
          <div className="palette-title" style={{ marginBottom: 0 }}>Agentes</div>
          <button className="btn btn-primary btn-sm" onClick={() => setShowNewAgent(true)}>
            <Plus size={13} /> Nuevo
          </button>
        </div>
        {paletteAgents.map(agent => (
          <div
            key={agent.id}
            className="palette-node"
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData('application/agentId', agent.id);
              e.dataTransfer.effectAllowed = 'move';
            }}
          >
            <div className="palette-node-icon" style={{ background: `${agent.color}20` }}>
              {agent.emoji}
            </div>
            <div>
              <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600 }}>{agent.label}</div>
              <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>{agent.desc}</div>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                style={{ marginTop: 'var(--space-2)', paddingInline: 0 }}
                draggable={false}
                onMouseDown={(event) => event.stopPropagation()}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setEditAgent(agent);
                }}
              >
                <Pencil size={12} /> Editar
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Canvas */}
      <div className="flow-canvas-area" ref={reactFlowWrapper}>
        <ReactFlow
          nodes={displayNodes}
          edges={displayEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          isValidConnection={isValidConnection}
          onInit={setRfInstance}
          onDrop={onDrop}
          onDragOver={onDragOver}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          deleteKeyCode={['Backspace', 'Delete']}
        >
          <Background variant="dots" gap={20} size={1} />
          <Controls />
          <MiniMap
            nodeColor={(n) => {
              if (n.type === 'condition') return 'var(--agent-review)';
              return n.data?.color || agentMeta(n.data?.agentId)?.color || 'var(--neutral-60)';
            }}
            maskColor="rgba(244,246,249,0.6)"
          />

          {issues.length > 0 && (
            <Panel position="bottom-left">
              <ul className="flow-issues" aria-label="Problemas del flujo" role="status">
                {issues.map((issue, i) => (
                  <li key={`${issue.code}-${i}`} className={`flow-issue flow-issue-${issue.severity}`}>
                    <AlertTriangle size={14} aria-hidden="true" />
                    <span>
                      <span className="sr-only">{issue.severity === ERROR ? 'Error: ' : 'Aviso: '}</span>
                      {issue.message}
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          {/* Toolbar */}
          <Panel position="top-center">
            <div className="flow-toolbar">
              <input
                className="input"
                style={{ width: 200, padding: '6px 10px' }}
                value={flowName}
                onChange={e => setFlowName(e.target.value)}
                placeholder="Nombre del flujo"
              />
              <div className="divider" style={{ width: 1, height: 24, margin: '0 4px' }} />
              <button className="btn btn-ghost btn-sm btn-icon" title="Limpiar canvas"
                onClick={() => { setNodes([]); setEdges([]); }}>
                <Trash2 size={15} />
              </button>
              <button className="btn btn-secondary btn-sm" onClick={handleSave} disabled={saving}>
                <Save size={14} />
                {saving ? 'Guardando…' : 'Guardar'}
              </button>
              <button className="btn btn-primary btn-sm" onClick={() => setShowRunModal(true)}
                disabled={nodes.filter(n => n.type === 'agent').length === 0 || errors.length > 0}
                title={errors.length > 0 ? errors[0].message : undefined}>
                <Play size={14} />
                Ejecutar
              </button>
            </div>
          </Panel>
        </ReactFlow>

        {/* Empty state */}
        {nodes.length === 0 && (
          <div className="flow-empty">
            <EmptyState
              icon={<GitBranch size={28} />}
              title="Diseña tu pipeline"
              description="Arrastra agentes desde el panel izquierdo al canvas para crear tu flujo de trabajo."
            />
          </div>
        )}
      </div>

      {/* Run Modal */}
      {showRunModal && (
        <Modal onClose={() => setShowRunModal(false)} title="Ejecutar pipeline">
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
              {existingArticleId ? (
                <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-muted)', margin: 0 }}>
                  Re-ejecutando pipeline <strong style={{ color: 'var(--text-primary)' }}>{flowName}</strong> sobre el artículo existente. Puedes cambiar el título a continuación.
                </p>
              ) : (
                <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-muted)', margin: 0 }}>
                  Se creará un nuevo artículo y se ejecutará el pipeline <strong style={{ color: 'var(--text-primary)' }}>{flowName}</strong> sobre él.
                </p>
              )}

              <div className="input-group">
                <label htmlFor="run-title" className="input-label">
                  Título del artículo
                  {existingArticleId && <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6 }}>— opcional, deja igual para mantener el actual</span>}
                </label>
                <input
                  id="run-title"
                  className="input"
                  placeholder={existingArticleId ? existingArticleTitle : 'Ej: El impacto del cambio climático en ecosistemas marinos'}
                  value={runTitle}
                  onChange={e => setRunTitle(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && document.getElementById('kw-input')?.focus()}
                  autoFocus
                />
              </div>

              <div className="input-group">
                <label htmlFor="run-description" className="input-label">
                  Descripción / enfoque
                  <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6 }}>— opcional</span>
                </label>
                <textarea
                  id="run-description"
                  className="input"
                  rows={3}
                  placeholder="Ej: Enfocado en arrecifes de coral del Caribe, con énfasis en acidificación oceánica y pérdida de biodiversidad post-2010."
                  value={runDescription}
                  onChange={e => setRunDescription(e.target.value)}
                  style={{ resize: 'vertical', fontSize: 'var(--font-size-sm)' }}
                />
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginTop: 4 }}>
                  El <strong>Investigador</strong> la usa para afinar la búsqueda semántica. El <strong>Redactor</strong> la recibe como instrucción de enfoque en el prompt.
                </div>
              </div>

              {/* Notas del enjambre (SPEC-030 / T18.3 / AC3) */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label htmlFor="run-notes" style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500 }}>
                  Notas para el enjambre
                  <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6 }}>— opcional</span>
                </label>
                <textarea
                  id="run-notes"
                  className="input"
                  rows={3}
                  maxLength={MAX_SWARM_NOTES}
                  placeholder="Ej: Evita comparaciones con el estudio de 2019; el revisor anterior las marcó como poco sólidas."
                  value={runNotes}
                  onChange={e => setRunNotes(e.target.value)}
                  style={{ resize: 'vertical', fontSize: 'var(--font-size-sm)' }}
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8,
                  fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
                  <span>
                    Se pasan como <strong>dato</strong>, no como instrucción: el agente las lee
                    como contexto y no cambian sus reglas. Quedan en la traza.
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', flexShrink: 0,
                    color: runNotes.length >= MAX_SWARM_NOTES ? 'var(--warning)' : undefined }}>
                    {runNotes.length}/{MAX_SWARM_NOTES}
                  </span>
                </div>
              </div>

              {/* Modo de aprendizaje del formato (SPEC-030 / T18.5 / AC6) */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500 }}>
                  Cómo se aprende el formato
                </span>
                <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
                  {Object.entries(FORMAT_MODES).map(([clave, modo]) => (
                    <label key={clave}
                      title={modo.detail}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        fontSize: 'var(--font-size-sm)',
                        cursor: modo.available ? 'pointer' : 'not-allowed',
                        opacity: modo.available ? 1 : 0.55,
                      }}>
                      <input
                        type="radio"
                        name="format-mode"
                        value={clave}
                        checked={runFormatMode === clave}
                        disabled={!modo.available}
                        onChange={() => setRunFormatMode(clave)}
                      />
                      {modo.label}
                      {!modo.available && (
                        <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
                          — no disponible
                        </span>
                      )}
                    </label>
                  ))}
                </div>
                {/* El motivo se enseña, no se esconde: una opción que no aparece
                    parece no existir, y esta existe y se está decidiendo. */}
                {!FORMAT_MODES[runFormatMode]?.available ? null : (
                  <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
                    {FORMAT_MODES.finetune.label}: {FORMAT_MODES.finetune.detail}
                  </div>
                )}
              </div>

              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowAdvanced(v => !v)}
                style={{ alignSelf: 'flex-start', color: 'var(--text-muted)' }}
              >
                {showAdvanced ? '▾' : '▸'} Opciones avanzadas (palabras clave, estructura)
              </button>
              {showAdvanced && (<>
              <div className="input-group">
                <label htmlFor="kw-input" className="input-label">
                  Palabras clave
                  <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6 }}>— orientan la búsqueda del Investigador</span>
                </label>
                <div style={{
                  display: 'flex', flexWrap: 'wrap', gap: 6, padding: '6px 10px',
                  background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-md)', minHeight: 42, alignItems: 'center',
                }}>
                  {runKeywords.map(kw => (
                    <span key={kw} style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      background: 'rgba(99,102,241,0.18)', color: 'var(--violet-40)',
                      borderRadius: 20, padding: '2px 10px', fontSize: 'var(--font-size-xs)', fontWeight: 500,
                    }}>
                      {kw}
                      <button
                        type="button"
                        onClick={() => setRunKeywords(ks => ks.filter(k => k !== kw))}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--violet-40)', lineHeight: 1, padding: 0 }}
                        aria-label={`Eliminar keyword ${kw}`}
                      >×</button>
                    </span>
                  ))}
                  <input
                    id="kw-input"
                    style={{ border: 'none', background: 'transparent', fontSize: 'var(--font-size-sm)', color: 'var(--text-primary)', minWidth: 120, flex: 1 }}
                    placeholder={runKeywords.length === 0 ? 'Escribe y pulsa Enter o coma…' : ''}
                    value={runKeywordInput}
                    onChange={e => setRunKeywordInput(e.target.value)}
                    onKeyDown={e => {
                      if ((e.key === 'Enter' || e.key === ',') && runKeywordInput.trim()) {
                        e.preventDefault();
                        const kw = runKeywordInput.trim().replace(/,$/, '');
                        if (kw && !runKeywords.includes(kw)) setRunKeywords(ks => [...ks, kw]);
                        setRunKeywordInput('');
                      } else if (e.key === 'Backspace' && !runKeywordInput && runKeywords.length > 0) {
                        setRunKeywords(ks => ks.slice(0, -1));
                      }
                    }}
                    aria-label="Añadir palabra clave"
                  />
                </div>
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginTop: 4 }}>
                  Si no se proporcionan, se extraen automáticamente del título.
                </div>
              </div>

              <div className="input-group">
                <label htmlFor="run-outline" className="input-label">
                  Estructura / Esquema del artículo
                  <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6 }}>— opcional</span>
                </label>
                <textarea
                  id="run-outline"
                  className="input"
                  rows={3}
                  placeholder="Ej:&#10;- Introducción: Contexto del cambio climático&#10;- Sección 1: Acidificación oceánica&#10;- Sección 2: Consecuencias ecológicas&#10;- Conclusiones generales"
                  value={runOutline}
                  onChange={e => setRunOutline(e.target.value)}
                  style={{ resize: 'vertical', fontSize: 'var(--font-size-sm)' }}
                />
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginTop: 4 }}>
                  Define las secciones, subsecciones o títulos creativos que el <strong>Redactor</strong> debe seguir obligatoriamente.
                </div>
              </div>
              </>)}

              <div className="input-group">
                <label className="input-label">
                  Fuentes de información (RAG)
                  <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6 }}>— opcional</span>
                </label>
                <input ref={runFileRef} type="file" accept=".txt,.md,.pdf,.docx" style={{ display: 'none' }} onChange={onRunFileSelected} />
                <button className="btn btn-ghost btn-sm" onClick={handleRunUpload} disabled={uploadingDoc} style={{ marginBottom: 8 }}>
                  <Upload size={13} /> {uploadingDoc ? 'Subiendo…' : 'Subir documento'}
                </button>
                <div style={{ maxHeight: 140, overflowY: 'auto', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-sm)', padding: 6 }}>
                  {loadingDocs ? (
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', padding: 6 }}>Cargando documentos…</div>
                  ) : runDocs.length === 0 ? (
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', padding: 6 }}>
                      No hay documentos. Sube uno o continúa sin fuentes.
                    </div>
                  ) : runDocs.map(d => (
                    <label key={d.doc_id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 6px', cursor: 'pointer', fontSize: 'var(--font-size-xs)' }}>
                      <input
                        type="checkbox"
                        checked={selectedDocIds.includes(d.doc_id)}
                        onChange={e => setSelectedDocIds(ids => e.target.checked ? [...ids, d.doc_id] : ids.filter(x => x !== d.doc_id))}
                      />
                      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.filename || d.doc_id}</span>
                      <span style={{ color: 'var(--text-muted)' }}>{d.collection}</span>
                    </label>
                  ))}
                </div>
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginTop: 4 }}>
                  Selecciona los documentos que el <strong>Investigador</strong> usará como fuentes. Si no seleccionas ninguno, buscará en toda la colección.
                </div>
              </div>

              <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', padding: 'var(--space-3)', fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
                <strong style={{ color: 'var(--text-secondary)' }}>Secuencia:</strong>{' '}
                {nodes.filter(n => n.type === 'agent').map((n) => {
                  const meta = agentMeta(n.data?.agentId) || {};
                  return `${n.data?.emoji || meta.emoji || '🤖'} ${n.data?.label || meta.label || n.data?.agentId}`;
                }).join(' → ')}
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setShowRunModal(false)}>Cancelar</button>
              <button className="btn btn-primary" onClick={handleRun}>
                <Play size={14} /> Ejecutar pipeline
              </button>
            </div>
        </Modal>
      )}

      {editAgent && (
        <AgentEditorModal
          agent={editAgent}
          isBuiltin={builtinIds().has(editAgent.id)}
          models={models}
          onClose={() => setEditAgent(null)}
          onSaved={async () => {
            setEditAgent(null);
            await loadPaletteAgents();
          }}
          onDeleted={(id) => {
            setEditAgent(null);
            setPaletteAgents((current) => current.filter((agent) => agent.id !== id));
            setNodes((current) => current.filter((node) => node.data?.agentId !== id));
          }}
        />
      )}

      {showNewAgent && (
        <AgentCreateModal
          builtInIds={builtinIds()}
          onClose={() => setShowNewAgent(false)}
          onCreate={async (payload) => {
            await agentsApi.createClaudeDef(payload);
            toast.success(`Agente "${payload.name}" creado`);
            await loadPaletteAgents();
          }}
        />
      )}
    </div>
  );
}
