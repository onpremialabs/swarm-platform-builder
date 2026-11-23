import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { runTarget } from '../runTarget';
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
import { Trans, translate, useTranslation } from '../i18n';

//: Agentes de serie: los del proyecto activo, más el orquestador, que no es
//: un nodo del pipeline (T8.6).
const builtinIds = () => new Set([...agentIds(), 'orquestador']);

let nodeId = 100;
const newId = () => `node_${++nodeId}`;

export default function FlowDesignerPage() {
  const { t } = useTranslation();
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
      const withLabel = { ...e, ariaLabel: t('flowDesigner.edgeAria', { from: names.get(e.source), to: names.get(e.target) }) };
      return marks.has(e.id)
        ? { ...withLabel, className: `flow-issue-${marks.get(e.id)}`, style: { ...e.style, stroke: `var(--${marks.get(e.id) === ERROR ? 'error' : 'warning'})` } }
        : withLabel;
    });
  }, [nodes, edges, issues, t]);

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
      desc: meta.desc || translate('flowDesigner.profileDesc', { slug: agent.slug || agent.id }),
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
        toast((aviso) => (
          <span style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {t('flowDesigner.draftNotice')}
            <button className="btn btn-primary btn-sm" onClick={() => {
              setNodes(draft.draftNodes);
              setEdges(draft.draftEdges);
              setFlowName(draft.draftName);
              toast.dismiss(aviso.id);
            }}>{t('flowDesigner.restore')}</button>
            <button className="btn btn-ghost btn-sm" onClick={() => {
              clearLocalDraft(); toast.dismiss(aviso.id);
            }}>{t('flowDesigner.discard')}</button>
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
      toast.success(t('flowDesigner.saved'));
    } catch (err) {
      toast.error(issueFromError(err) || t('flowDesigner.saveError'));
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
      // Upload to the investigador bucket so it is available as a source
      // A qué agente pertenecen las fuentes que se suben desde el lienzo lo
      // dice el proyecto: en AlejandrIA es el investigador (T8.6).
      const res = await agentsApi.uploadRagDocument(ragOwner(), file);
      toast.success(
        res?.title
          ? t(res.authors ? 'flowDesigner.docAddedWithAuthors' : 'flowDesigner.docAdded', { title: res.title, authors: res.authors })
          : t('flowDesigner.docAddedFile', { name: file.name })
      );
      const data = await agentsApi.getLibraryDocs();
      setRunDocs(flattenLibrary(data));
      if (res?.doc_id) setSelectedDocIds(ids => [...new Set([...ids, res.doc_id])]);
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('flowDesigner.docUploadError'));
    } finally {
      setUploadingDoc(false);
    }
  };

  const handleRun = async () => {
    const titleValue = runTitle.trim();
    if (!titleValue && !existingArticleId) { toast.error(t('flowDesigner.titleRequired')); return; }
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
      // Inject selected RAG documents as the sources of the Investigador
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
        }
      });
    } catch (err) {
      console.error('Error al iniciar pipeline', err);
      toast.error(issueFromError(err) || err?.response?.data?.detail || t('flowDesigner.runError'));
    }
  };

  return (
    <div className="flow-designer-layout">
      {/* Agent Palette */}
      <div className="flow-palette">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
          <div className="palette-title" style={{ marginBottom: 0 }}>{t('flowDesigner.palette.title')}</div>
          <button className="btn btn-primary btn-sm" onClick={() => setShowNewAgent(true)}>
            <Plus size={13} /> {t('flowDesigner.palette.new')}
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
                <Pencil size={12} /> {t('flowDesigner.palette.edit')}
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
              <ul className="flow-issues" aria-label={t('flowDesigner.issuesAria')} role="status">
                {issues.map((issue, i) => (
                  <li key={`${issue.code}-${i}`} className={`flow-issue flow-issue-${issue.severity}`}>
                    <AlertTriangle size={14} aria-hidden="true" />
                    <span>
                      <span className="sr-only">{issue.severity === ERROR ? t('flowDesigner.issueError') : t('flowDesigner.issueWarning')}</span>
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
                placeholder={t('flowDesigner.flowNamePlaceholder')}
              />
              <div className="divider" style={{ width: 1, height: 24, margin: '0 4px' }} />
              <button className="btn btn-ghost btn-sm btn-icon" title={t('flowDesigner.clearCanvas')}
                onClick={() => { setNodes([]); setEdges([]); }}>
                <Trash2 size={15} />
              </button>
              <button className="btn btn-secondary btn-sm" onClick={handleSave} disabled={saving}>
                <Save size={14} />
                {saving ? t('flowDesigner.saving') : t('flowDesigner.save')}
              </button>
              <button className="btn btn-primary btn-sm" onClick={() => setShowRunModal(true)}
                disabled={nodes.filter(n => n.type === 'agent').length === 0 || errors.length > 0}
                title={errors.length > 0 ? errors[0].message : undefined}>
                <Play size={14} />
                {t('flowDesigner.run')}
              </button>
            </div>
          </Panel>
        </ReactFlow>

        {/* Empty state */}
        {nodes.length === 0 && (
          <div className="flow-empty">
            <EmptyState
              icon={<GitBranch size={28} />}
              title={t('flowDesigner.emptyTitle')}
              description={t('flowDesigner.emptyDescription')}
            />
          </div>
        )}
      </div>

      {/* Run Modal */}
      {showRunModal && (
        <Modal onClose={() => setShowRunModal(false)} title={t('flowDesigner.runModal.title')}>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
              {existingArticleId ? (
                <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-muted)', margin: 0 }}>
                  <Trans i18nKey="flowDesigner.runModal.rerun" values={{ name: flowName }} components={{ strong: <strong style={{ color: 'var(--text-primary)' }} /> }} />
                </p>
              ) : (
                <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-muted)', margin: 0 }}>
                  <Trans i18nKey="flowDesigner.runModal.new" values={{ name: flowName }} components={{ strong: <strong style={{ color: 'var(--text-primary)' }} /> }} />
                </p>
              )}

              <div className="input-group">
                <label htmlFor="run-title" className="input-label">
                  {t('flowDesigner.runModal.titleLabel')}
                  {existingArticleId && <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6 }}>{t('flowDesigner.runModal.titleKeep')}</span>}
                </label>
                <input
                  id="run-title"
                  className="input"
                  placeholder={existingArticleId ? existingArticleTitle : t('flowDesigner.runModal.titlePlaceholder')}
                  value={runTitle}
                  onChange={e => setRunTitle(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && document.getElementById('kw-input')?.focus()}
                  autoFocus
                />
              </div>

              <div className="input-group">
                <label htmlFor="run-description" className="input-label">
                  {t('flowDesigner.runModal.descriptionLabel')}
                  <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6 }}>{t('flowDesigner.runModal.optional')}</span>
                </label>
                <textarea
                  id="run-description"
                  className="input"
                  rows={3}
                  placeholder={t('flowDesigner.runModal.descriptionPlaceholder')}
                  value={runDescription}
                  onChange={e => setRunDescription(e.target.value)}
                  style={{ resize: 'vertical', fontSize: 'var(--font-size-sm)' }}
                />
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginTop: 4 }}>
                  <Trans i18nKey="flowDesigner.runModal.descriptionHelp" />
                </div>
              </div>

              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowAdvanced(v => !v)}
                style={{ alignSelf: 'flex-start', color: 'var(--text-muted)' }}
              >
                {showAdvanced ? '▾' : '▸'} {t('flowDesigner.runModal.advanced')}
              </button>
              {showAdvanced && (<>
              <div className="input-group">
                <label htmlFor="kw-input" className="input-label">
                  {t('flowDesigner.runModal.keywordsLabel')}
                  <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6 }}>{t('flowDesigner.runModal.keywordsHint')}</span>
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
                        aria-label={t('flowDesigner.runModal.removeKeyword', { keyword: kw })}
                      >×</button>
                    </span>
                  ))}
                  <input
                    id="kw-input"
                    style={{ border: 'none', background: 'transparent', fontSize: 'var(--font-size-sm)', color: 'var(--text-primary)', minWidth: 120, flex: 1 }}
                    placeholder={runKeywords.length === 0 ? t('flowDesigner.runModal.keywordPlaceholder') : ''}
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
                    aria-label={t('flowDesigner.runModal.addKeyword')}
                  />
                </div>
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginTop: 4 }}>
                  {t('flowDesigner.runModal.keywordsHelp')}
                </div>
              </div>

              <div className="input-group">
                <label htmlFor="run-outline" className="input-label">
                  {t('flowDesigner.runModal.outlineLabel')}
                  <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6 }}>{t('flowDesigner.runModal.optional')}</span>
                </label>
                <textarea
                  id="run-outline"
                  className="input"
                  rows={3}
                  placeholder={t('flowDesigner.runModal.outlinePlaceholder')}
                  value={runOutline}
                  onChange={e => setRunOutline(e.target.value)}
                  style={{ resize: 'vertical', fontSize: 'var(--font-size-sm)' }}
                />
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginTop: 4 }}>
                  <Trans i18nKey="flowDesigner.runModal.outlineHelp" />
                </div>
              </div>
              </>)}

              <div className="input-group">
                <label className="input-label">
                  {t('flowDesigner.runModal.sourcesLabel')}
                  <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6 }}>{t('flowDesigner.runModal.optional')}</span>
                </label>
                <input ref={runFileRef} type="file" accept=".txt,.md,.pdf,.docx" style={{ display: 'none' }} onChange={onRunFileSelected} />
                <button className="btn btn-ghost btn-sm" onClick={handleRunUpload} disabled={uploadingDoc} style={{ marginBottom: 8 }}>
                  <Upload size={13} /> {uploadingDoc ? t('flowDesigner.runModal.uploading') : t('flowDesigner.runModal.upload')}
                </button>
                <div style={{ maxHeight: 140, overflowY: 'auto', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-sm)', padding: 6 }}>
                  {loadingDocs ? (
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', padding: 6 }}>{t('flowDesigner.runModal.loadingDocs')}</div>
                  ) : runDocs.length === 0 ? (
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', padding: 6 }}>
                      {t('flowDesigner.runModal.noDocs')}
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
                  <Trans i18nKey="flowDesigner.runModal.sourcesHelp" />
                </div>
              </div>

              <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', padding: 'var(--space-3)', fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
                <strong style={{ color: 'var(--text-secondary)' }}>{t('flowDesigner.runModal.sequence')}</strong>{' '}
                {nodes.filter(n => n.type === 'agent').map((n) => {
                  const meta = agentMeta(n.data?.agentId) || {};
                  return `${n.data?.emoji || meta.emoji || '🤖'} ${n.data?.label || meta.label || n.data?.agentId}`;
                }).join(' → ')}
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setShowRunModal(false)}>{t('flowDesigner.runModal.cancel')}</button>
              <button className="btn btn-primary" onClick={handleRun}>
                <Play size={14} /> {t('flowDesigner.runModal.runPipeline')}
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
            toast.success(t('flowDesigner.agentCreated', { name: payload.name }));
            await loadPaletteAgents();
          }}
        />
      )}
    </div>
  );
}
