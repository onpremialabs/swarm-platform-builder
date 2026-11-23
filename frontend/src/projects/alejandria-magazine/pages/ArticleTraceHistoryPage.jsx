import React, { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import {
  Activity, ArrowLeft, BarChart3, CheckCircle, CircleAlert, Clock, Database,
  Download, FileText, Info, Layers, List, RefreshCw, ShieldCheck, XCircle,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { agentsApi } from '../../../platform/api/agents';
import { agentMeta } from '../../../platform/agentCatalog';
import { useProjectStore } from '../../../platform/store/projectStore';
import ArticleCitations from '../components/ArticleCitations';
import './article-trace-history.css';

const tabs = [['summary','Resumen',Activity],['steps','Trazas por agente',Layers],['logs','Logs',List],['metrics','Métricas',BarChart3],['sources','Fuentes',Database],['integrity','Integridad',ShieldCheck]];
const num = n => Number(n || 0).toLocaleString('es-CL');
const duration = ms => { const s = Math.round(Number(ms || 0)/1000); return ms > 0 && ms < 1000 ? `${Math.round(ms)} ms` : s < 60 ? `${s} s` : `${Math.floor(s/60)} min ${s%60} s`; };
const date = value => value ? new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString('es-CL') : '—';
const name = agent => agentMeta(agent)?.label || agent;
const labels = { completed:'Completada',failed:'Fallida',running:'En curso',cancelled:'Cancelada',error:'Error' };
const statusIcons = {
  completed: CheckCircle, failed: XCircle, running: Clock, cancelled: XCircle, error: CircleAlert,
};

function Status({ value }) {
  const Icon = statusIcons[value] || Info;
  return (
    <span className={`ath-badge ath-${value}`}>
      <Icon size={14} strokeWidth={1.5} aria-hidden="true" />
      {labels[value] || value}
    </span>
  );
}
function AgentIcon({agent}) {
  const meta = agentMeta(agent);
  const Icon = meta.icon || Activity;
  return <span className="ath-agent-icon" style={{color:meta.color || 'var(--brand)'}} aria-hidden="true"><Icon size={18} strokeWidth={1.5} /></span>;
}
function Card({title,children}) { return <section className="ath-card"><h2>{title}</h2>{children}</section>; }
function Json({value}) { return <pre className="ath-json">{JSON.stringify(value,null,2)}</pre>; }

export default function ArticleTraceHistoryPage() {
  const {id} = useParams();
  const projectId = useProjectStore(s => s.activeProject?.id);
  const [params,setParams] = useSearchParams();
  const requested = params.get('execution');
  const [history,setHistory] = useState(null);
  const [detail,setDetail] = useState(null);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const [refresh,setRefresh] = useState(0);
  const [tab,setTab] = useState('summary');
  const [agent,setAgent] = useState('');
  const [level,setLevel] = useState('');
  const [search,setSearch] = useState('');
  const [page,setPage] = useState(0);
  const [selected,setSelected] = useState(null);
  useEffect(() => {
    const control = new AbortController();
    setHistory(null); setDetail(null); setError('');
    agentsApi.getTraceHistory(id,control.signal).then(result => { if (!control.signal.aborted) setHistory({...result,projectId}); })
      .catch(e => { if (!control.signal.aborted) setError(e.response?.status === 403 ? 'No tienes permiso para consultar estas trazas.' : 'No se pudo cargar el historial.'); });
    return () => control.abort();
  },[id,projectId,refresh]);
  const currentHistory = history?.article_id === id && history?.projectId === projectId ? history : null;
  const executionId = requested || currentHistory?.executions[0]?.id;
  useEffect(() => {
    setDetail(null); setSelected(null); setAgent(''); setLevel(''); setSearch(''); setPage(0);
    if (!executionId || !currentHistory) {
      setBusy(false);
      return undefined;
    }
    const control = new AbortController(); setBusy(true); setError('');
    agentsApi.getTraceHistoryDetail(id,executionId,control.signal).then(result => { if (!control.signal.aborted) setDetail(result); })
      .catch(() => { if (!control.signal.aborted) setError('No se pudo cargar esta ejecución. Selecciona otra o vuelve a intentarlo.'); })
      .finally(() => { if (!control.signal.aborted) setBusy(false); });
    return () => control.abort();
  },[id,projectId,executionId,currentHistory]);
  const data = currentHistory && detail?.execution.id === executionId ? detail : null;
  const run = data?.execution;
  const steps = data?.steps || [];
  const sources = data?.sources || [];
  const searches = data?.searches || [];
  const agents = Object.values(steps.reduce((all,s) => { const a = all[s.agent_name] ||= {name:s.agent_name,steps:0,tokens:0,time:0,errors:0}; a.steps++; a.tokens+=(s.tokens_in||0)+(s.tokens_out||0); a.time+=s.latency_ms||0; a.errors+=!['completed','running'].includes(s.status)?1:0; return all; },{}));
  const logLevel = step => ['completed', 'running'].includes(step.status) ? 'INFO' : 'ERROR';
  const events = steps.filter(s => (!agent || s.agent_name===agent) && (!level || logLevel(s)===level) && (!search || `${s.agent_name} ${s.error_message||''} ${s.status} ${s.id}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())));
  const trace = steps.find(s=>s.id===selected);
  function exportTrace() {
    const rows = [{type:'manifest',schema_version:1,article_id:id,title:data.title,execution:run,integrity:data.integrity,scope:data.integrity_scope,searches:searches.length},...steps.map(s=>({type:'step',...s})),...searches.map(b=>({type:'search',...b}))];
    const blob = new Blob([rows.map(row=>JSON.stringify(row)).join('\n')+'\n'],{type:'application/x-ndjson'});
    const url=URL.createObjectURL(blob); const link=document.createElement('a'); link.href=url; link.download=`traza-${id}-${run.id}.jsonl`; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  return <div className="page-body ath-page">
    <Link className="ath-back" to="/dashboard/traceability"><ArrowLeft size={15}/>Volver a trazabilidad</Link>
    <header className="ath-header"><div><p className="ath-eyebrow">HISTORIAL DE GENERACIÓN</p><h1>{currentHistory?.title || 'Historial de trazas'}</h1><p>Consulta los pasos, decisiones y fuentes guardados de cada ejecución.</p></div><button className="btn btn-secondary btn-sm" disabled={busy} onClick={()=>setRefresh(n=>n+1)}><RefreshCw size={14}/>Actualizar</button></header>
    {error && (
      <div role="alert" className="ath-alert">
        <CircleAlert size={16} aria-hidden="true" />
        <span>{error}</span>
        <button className="btn btn-secondary btn-sm" onClick={() => setRefresh(n => n + 1)}>Reintentar</button>
      </div>
    )}
    {!currentHistory && !error && <p role="status">Cargando historial…</p>}
    {currentHistory && <><div className="ath-toolbar"><label>Ejecución <select className="input" aria-label="Seleccionar ejecución" value={executionId||''} onChange={e=>setParams({execution:e.target.value})}>{currentHistory.executions.map(e=><option key={e.id} value={e.id}>Ejecución {e.run_number} · {date(e.started_at)} · {labels[e.status]||e.status}</option>)}</select></label><button className="btn btn-secondary btn-sm" disabled={!data} onClick={exportTrace}><Download size={14}/>Exportar JSONL</button></div>
    {!currentHistory.executions.length && <Card title="Sin trazas guardadas"><p>No hay pasos conservados para este artículo. No es posible reconstruir su ejecución con la información disponible.</p></Card>}
    {busy && <p role="status">Cargando ejecución…</p>}
    {run && <><div className="ath-run-heading"><Status value={run.status}/>{run.recovered_failures>0 && <span>{num(run.recovered_failures)} fallos recuperados</span>}<span>Inicio: {date(run.started_at)}</span><span>Último paso guardado: {date(run.last_step_at)}</span></div>
      <nav className="ath-tabs" aria-label="Secciones del historial">{tabs.map(([key,label,Icon])=><button key={key} aria-pressed={tab===key} onClick={()=>setTab(key)}><Icon size={16} strokeWidth={1.5} aria-hidden="true" />{label}</button>)}</nav>
      {tab==='summary' && <><div className="ath-stats">{[['Intentos registrados',run.steps],['Tokens totales',num(run.tokens_in+run.tokens_out)],['Tiempo de agentes',duration(run.latency_ms)],['Intentos con error',run.failed_steps]].map(([label,value])=><div className="ath-stat" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><div className="ath-columns"><Card title="Recorrido de la ejecución"><div className="ath-timeline">{steps.map(s=><button key={s.id} onClick={()=>{setSelected(s.id);setTab('steps');}}><AgentIcon agent={s.agent_name}/><span><strong>{name(s.agent_name)}</strong><small>Vuelta {s.iteration+1} · {date(s.created_at)}</small></span><span>{duration(s.latency_ms)}</span><Status value={s.status}/></button>)}</div></Card><Card title="Resultado y decisiones"><p><Status value={run.status}/></p><p>{run.recovered_failures ? 'Hubo errores que se resolvieron mediante reintentos. Los intentos originales se conservan.' : 'El resultado se calcula a partir del último intento guardado de cada paso.'}</p>{steps.filter(s=>s.decision).map(s=><div className="ath-decision" key={s.id}><strong>{name(s.agent_name)} · vuelta {s.iteration+1}</strong>{s.decision.score != null && <p>Score del revisor: <strong>{s.decision.score}/100</strong></p>}{s.decision.coherent != null && <p>Coherencia: <strong>{s.decision.coherent ? 'Sí' : 'No'}</strong></p>}{s.decision.hitl_outcome && <p>Decisión humana: {s.decision.hitl_outcome}</p>}{s.rationale && <details><summary>Ver justificación</summary><p>{s.rationale}</p></details>}<details><summary>Metadatos de la decisión</summary><Json value={s.decision}/></details></div>)}<p className="ath-muted">El estado técnico no equivale a aprobación científica ni editorial. Los tiempos suman intentos; no representan el tiempo de reloj del pipeline.</p></Card></div></>}
      {tab==='steps' && <div className="ath-columns"><Card title="Trazas por agente"><div className="ath-timeline">{steps.map(s=><button key={s.id} aria-pressed={selected===s.id} onClick={()=>setSelected(s.id)}><AgentIcon agent={s.agent_name}/><span><strong>{name(s.agent_name)}</strong><small>{s.model||'Modelo no registrado'} · {num(s.tokens_in+s.tokens_out)} tokens</small></span><Status value={s.status}/></button>)}</div></Card><Card title={trace ? `Detalle · ${name(trace.agent_name)}` : 'Detalle del intento'}>{trace ? <><p><Status value={trace.status}/> · {duration(trace.latency_ms)}</p><p className="ath-muted">
        ID: <code>{trace.id}</code><br />
        Correlación: {trace.correlation_id ? <code>{trace.correlation_id}</code> : 'No registrada'}
      </p>{trace.error_message && <div className="ath-alert">
        <CircleAlert size={16} aria-hidden="true" />
        <span>{trace.error_message}</span>
      </div>}<details><summary>Entrada y parámetros</summary><Json value={{input:trace.input_digest,model:trace.model,params:trace.params}}/></details>{trace.output_text && <details open><summary>Salida guardada</summary><div className="ath-output"><ReactMarkdown>{trace.output_text}</ReactMarkdown></div></details>}<details><summary>Registro JSON completo</summary><Json value={trace}/></details></> : <p>Selecciona un intento para consultar su entrada, salida, modelo y metadatos.</p>}</Card></div>}
      {tab === 'logs' && (
        <Card title="Registros de los intentos">
          <p className="ath-muted">Cronología derivada de los pasos persistidos. Los eventos SSE y fragmentos de generación en vivo no están disponibles en este historial.</p>
          <div className="ath-filters">
            <label className="input-group">
              <span className="input-label">Buscar registros</span>
              <input className="input" type="search" placeholder="Buscar por mensaje o ID…" value={search}
                onChange={e => { setSearch(e.target.value); setPage(0); }} />
            </label>
            <label className="input-group">
              <span className="input-label">Agente</span>
              <select className="input" value={agent} onChange={e => { setAgent(e.target.value); setPage(0); }}>
                <option value="">Todos los agentes</option>
                {agents.map(a => <option key={a.name} value={a.name}>{name(a.name)}</option>)}
              </select>
            </label>
            <label className="input-group">
              <span className="input-label">Nivel</span>
              <select className="input" value={level} onChange={e => { setLevel(e.target.value); setPage(0); }}>
                <option value="">Todos los niveles</option>
                <option>INFO</option>
                <option>ERROR</option>
              </select>
            </label>
          </div>
          {events.length > 0 ? (
            <div className="ath-table-scroll">
              <table>
                <thead><tr>
                  <th scope="col">Hora de registro</th>
                  <th scope="col">Nivel</th>
                  <th scope="col">Agente</th>
                  <th scope="col">Mensaje</th>
                  <th scope="col">Detalle</th>
                </tr></thead>
                <tbody>
                  {events.slice(page * 20, page * 20 + 20).map(s => {
                    const severity = logLevel(s);
                    return (
                      <tr key={s.id}>
                        <td>{date(s.created_at)}</td>
                        <td><span className={`ath-badge ath-${severity.toLowerCase()}`}>{severity}</span></td>
                        <td>{name(s.agent_name)}</td>
                        <td>{s.error_message || labels[s.status] || s.status}</td>
                        <td><button className="btn btn-ghost btn-sm"
                          onClick={() => { setSelected(s.id); setTab('steps'); }}>Ver intento</button></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : <p>Sin registros que coincidan.</p>}
          <div className="ath-toolbar">
            <span>{events.length} registros · página {page + 1}</span>
            <div>
              <button className="btn btn-ghost btn-sm" disabled={!page} onClick={() => setPage(p => p - 1)}>Anterior</button>
              <button className="btn btn-ghost btn-sm" disabled={(page + 1) * 20 >= events.length}
                onClick={() => setPage(p => p + 1)}>Siguiente</button>
            </div>
          </div>
        </Card>
      )}
      {tab === 'metrics' && (
        <div className="ath-columns">
          {[['Tokens por agente', 'tokens'], ['Tiempo por agente', 'time']].map(([title, key]) => {
            const maximum = Math.max(1, ...agents.map(agent => agent[key]));
            return (
              <Card title={title} key={key}>
                {agents.map(agent => (
                  <div className="ath-bar-row" key={agent.name}>
                    <span>{name(agent.name)}</span>
                    <div className={`ath-bar ath-bar-${key}`} aria-hidden="true">
                      <span style={{ width: `${100 * agent[key] / maximum}%` }} />
                    </div>
                    <strong>{key === 'time' ? duration(agent.time) : num(agent.tokens)}</strong>
                    <small>{agent.steps} intentos · {agent.errors} errores</small>
                  </div>
                ))}
              </Card>
            );
          })}
          <Card title="Entrada y salida">
            <p>Tokens de entrada: <strong>{num(run.tokens_in)}</strong></p>
            <p>Tokens de salida: <strong>{num(run.tokens_out)}</strong></p>
            <p>Todos los intentos guardados se incluyen, también los fallidos.</p>
          </Card>
        </div>
      )}
      {tab==='sources' && <ArticleCitations articleId={id} projectId={projectId} />}
      {tab==='sources' && <Card title={`Fuentes recuperadas (${sources.length})`}><p className="ath-muted">Recuperación RAG registrada; no demuestra que el artículo final cite estas fuentes. No se guardó el texto completo de los fragmentos en estas trazas.</p>{sources.length ? sources.map(s=><article className="ath-source" key={s.doc_id}><h3><FileText size={16}/>{s.title||s.doc_id}</h3><p>{s.authors||'Autoría no registrada'} · Colección: {s.collection||'—'}</p><p>Similitud registrada: {Number(s.score||0).toFixed(2)} · Recuperada por: {(s.used_by||[]).map(name).join(', ')}</p><details><summary>{s.chunk_ids?.length||0} fragmentos registrados · Ver identificadores</summary><Json value={{doc_id:s.doc_id,chunk_ids:s.chunk_ids}}/></details></article>) : <p>No hay fuentes recuperadas registradas para esta ejecución.</p>}</Card>}
      {tab==='sources' && <Card title={`Búsquedas bibliográficas (${searches.length})`}><p className="ath-muted">Registro reproducible de cada búsqueda: bases consultadas, cadena, filtros y fecha (UTC). Solo se guarda la cadena de búsqueda y recuentos, no el texto del manuscrito. Incluye todas las búsquedas del artículo y se exporta en el JSONL.</p>{searches.length ? searches.map(b=><article className="ath-source" key={b.id}><h3><Database size={16}/>{b.query}</h3><p>Fecha: {date(b.searched_at)} · Estado: {b.status} · Bases: {(b.sources||[]).join(', ')||'—'}</p><p>Resultados: {b.result_count} · Verificados: {b.verified_count}{Object.keys(b.discarded||{}).length ? ` · Descartados: ${Object.entries(b.discarded).map(([k,v])=>`${k} ${v}`).join(', ')}` : ''}</p><details><summary>Filtros y detalle por base</summary><Json value={{filters:b.filters,per_source:b.per_source}}/></details></article>) : <p>No hay búsquedas bibliográficas registradas para este artículo.</p>}</Card>}
      {tab==='integrity' && <Card title="Integridad de los pasos"><p>{data.integrity.status === 'intacta'
        ? <span className="ath-badge ath-completed"><ShieldCheck size={14} aria-hidden="true" />Cadena verificada</span>
        : data.integrity.status === 'rota'
          ? <span className="ath-badge ath-error"><CircleAlert size={14} aria-hidden="true" />Se detectaron inconsistencias</span>
          : <span className="ath-badge"><Info size={14} aria-hidden="true" />Sin hashes para verificar</span>}
      </p><p>{data.integrity.verified} pasos verificados · {data.integrity.unchained} sin hash</p><p className="ath-muted">{data.integrity_scope}</p>{data.integrity.issues.length>0 && <Json value={data.integrity.issues}/>}</Card>}
      <p className="ath-footnote">Vista de consulta de datos guardados. No inicia, reanuda ni detiene pipelines. Identificador de ejecución: <code>{run.id}</code>.</p>
    </> }</>}
  </div>;
}
