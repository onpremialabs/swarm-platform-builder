import React, { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { Activity, ArrowLeft, BarChart3, Database, Download, FileText, Layers, List, RefreshCw, ShieldCheck } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { agentsApi } from '../../../platform/api/agents';
import { agentMeta } from '../../../platform/agentCatalog';
import { useProjectStore } from '../../../platform/store/projectStore';
import './article-trace-history.css';

const tabs = [['summary','Resumen',Activity],['steps','Trazas por agente',Layers],['logs','Logs',List],['metrics','Métricas',BarChart3],['sources','Fuentes',Database],['integrity','Integridad',ShieldCheck]];
const num = n => Number(n || 0).toLocaleString('es-CL');
const duration = ms => { const s = Math.round(Number(ms || 0)/1000); return ms > 0 && ms < 1000 ? `${Math.round(ms)} ms` : s < 60 ? `${s} s` : `${Math.floor(s/60)} min ${s%60} s`; };
const date = value => value ? new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString('es-CL') : '—';
const name = agent => agentMeta(agent)?.label || agent;
const labels = { completed:'Completada',failed:'Fallida',running:'En curso',cancelled:'Cancelada',error:'Error' };
function Status({value}) { return <span className={`ath-badge ath-${value}`}>{labels[value] || value}</span>; }
function AgentIcon({agent}) {
  const meta = agentMeta(agent);
  const Icon = meta.icon || Activity;
  return <span className="ath-agent-icon" style={{color:meta.color || 'var(--brand)'}} aria-hidden="true"><Icon size={19}/></span>;
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
    if (!executionId || !currentHistory) return undefined;
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
  const agents = Object.values(steps.reduce((all,s) => { const a = all[s.agent_name] ||= {name:s.agent_name,steps:0,tokens:0,time:0,errors:0}; a.steps++; a.tokens+=(s.tokens_in||0)+(s.tokens_out||0); a.time+=s.latency_ms||0; a.errors+=!['completed','running'].includes(s.status)?1:0; return all; },{}));
  const events = steps.filter(s => (!agent || s.agent_name===agent) && (!level || (s.status==='completed'?'INFO':'ERROR')===level) && (!search || `${s.agent_name} ${s.error_message||''} ${s.status} ${s.id}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())));
  const trace = steps.find(s=>s.id===selected);
  function exportTrace() {
    const rows = [{type:'manifest',schema_version:1,article_id:id,title:data.title,execution:run,integrity:data.integrity,scope:data.integrity_scope},...steps.map(s=>({type:'step',...s}))];
    const blob = new Blob([rows.map(row=>JSON.stringify(row)).join('\n')+'\n'],{type:'application/x-ndjson'});
    const url=URL.createObjectURL(blob); const link=document.createElement('a'); link.href=url; link.download=`traza-${id}-${run.id}.jsonl`; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  return <div className="page-body ath-page">
    <Link className="ath-back" to="/dashboard/traceability"><ArrowLeft size={15}/>Volver a trazabilidad</Link>
    <header className="ath-header"><div><p className="ath-eyebrow">HISTORIAL DE GENERACIÓN</p><h1>{currentHistory?.title || 'Historial de trazas'}</h1><p>Consulta los pasos, decisiones y fuentes guardados de cada ejecución.</p></div><button className="btn btn-secondary btn-sm" disabled={busy} onClick={()=>setRefresh(n=>n+1)}><RefreshCw size={14}/>Actualizar</button></header>
    {error && <div role="alert" className="ath-alert">{error} <button className="btn btn-ghost btn-sm" onClick={()=>setRefresh(n=>n+1)}>Reintentar</button></div>}
    {!currentHistory && !error && <p role="status">Cargando historial…</p>}
    {currentHistory && <><div className="ath-toolbar"><label>Ejecución <select aria-label="Seleccionar ejecución" value={executionId||''} onChange={e=>setParams({execution:e.target.value})}>{currentHistory.executions.map(e=><option key={e.id} value={e.id}>Ejecución {e.run_number} · {date(e.started_at)} · {labels[e.status]||e.status}</option>)}</select></label><button className="btn btn-secondary btn-sm" disabled={!data} onClick={exportTrace}><Download size={14}/>Exportar JSONL</button></div>
    {!currentHistory.executions.length && <Card title="Sin trazas guardadas"><p>No hay pasos conservados para este artículo. No es posible reconstruir su ejecución con la información disponible.</p></Card>}
    {busy && <p role="status">Cargando ejecución…</p>}
    {run && <><div className="ath-run-heading"><Status value={run.status}/>{run.recovered_failures>0 && <span>{num(run.recovered_failures)} fallos recuperados</span>}<span>Inicio: {date(run.started_at)}</span><span>Último paso guardado: {date(run.last_step_at)}</span></div>
      <nav className="ath-tabs" aria-label="Secciones del historial">{tabs.map(([key,label,Icon])=><button key={key} aria-pressed={tab===key} onClick={()=>setTab(key)}><Icon size={16}/>{label}</button>)}</nav>
      {tab==='summary' && <><div className="ath-stats">{[['Intentos registrados',run.steps],['Tokens totales',num(run.tokens_in+run.tokens_out)],['Tiempo de agentes',duration(run.latency_ms)],['Intentos con error',run.failed_steps]].map(([label,value])=><div className="ath-stat" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><div className="ath-columns"><Card title="Recorrido de la ejecución"><div className="ath-timeline">{steps.map(s=><button key={s.id} onClick={()=>{setSelected(s.id);setTab('steps');}}><AgentIcon agent={s.agent_name}/><span><strong>{name(s.agent_name)}</strong><small>Vuelta {s.iteration+1} · {date(s.created_at)}</small></span><span>{duration(s.latency_ms)}</span><Status value={s.status}/></button>)}</div></Card><Card title="Resultado y decisiones"><p><Status value={run.status}/></p><p>{run.recovered_failures ? 'Hubo errores que se resolvieron mediante reintentos. Los intentos originales se conservan.' : 'El resultado se calcula a partir del último intento guardado de cada paso.'}</p>{steps.filter(s=>s.decision).map(s=><div className="ath-decision" key={s.id}><strong>{name(s.agent_name)} · vuelta {s.iteration+1}</strong>{s.decision.score != null && <p>Score del revisor: <strong>{s.decision.score}/100</strong></p>}{s.decision.coherent != null && <p>Coherencia: <strong>{s.decision.coherent ? 'Sí' : 'No'}</strong></p>}{s.decision.hitl_outcome && <p>Decisión humana: {s.decision.hitl_outcome}</p>}{s.rationale && <details><summary>Ver justificación</summary><p>{s.rationale}</p></details>}<details><summary>Metadatos de la decisión</summary><Json value={s.decision}/></details></div>)}<p className="ath-muted">El estado técnico no equivale a aprobación científica ni editorial. Los tiempos suman intentos; no representan el tiempo de reloj del pipeline.</p></Card></div></>}
      {tab==='steps' && <div className="ath-columns"><Card title="Trazas por agente"><div className="ath-timeline">{steps.map(s=><button key={s.id} aria-pressed={selected===s.id} onClick={()=>setSelected(s.id)}><AgentIcon agent={s.agent_name}/><span><strong>{name(s.agent_name)}</strong><small>{s.model||'Modelo no registrado'} · {num(s.tokens_in+s.tokens_out)} tokens</small></span><Status value={s.status}/></button>)}</div></Card><Card title={trace ? `Detalle · ${name(trace.agent_name)}` : 'Detalle del intento'}>{trace ? <><p><Status value={trace.status}/> · {duration(trace.latency_ms)}</p><p className="ath-muted">ID: {trace.id}<br/>Correlación: {trace.correlation_id||'No registrada'}</p>{trace.error_message && <p className="ath-alert">{trace.error_message}</p>}<details><summary>Entrada y parámetros</summary><Json value={{input:trace.input_digest,model:trace.model,params:trace.params}}/></details>{trace.output_text && <details open><summary>Salida guardada</summary><div className="ath-output"><ReactMarkdown>{trace.output_text}</ReactMarkdown></div></details>}<details><summary>Registro JSON completo</summary><Json value={trace}/></details></> : <p>Selecciona un intento para consultar su entrada, salida, modelo y metadatos.</p>}</Card></div>}
      {tab==='logs' && <Card title="Registros de los intentos"><p className="ath-muted">Cronología derivada de los pasos persistidos. Los eventos SSE y fragmentos de generación en vivo no están disponibles en este historial.</p><div className="ath-filters"><input aria-label="Buscar registros" placeholder="Buscar en registros…" value={search} onChange={e=>{setSearch(e.target.value);setPage(0);}}/><select aria-label="Filtrar agente" value={agent} onChange={e=>{setAgent(e.target.value);setPage(0);}}><option value="">Todos los agentes</option>{agents.map(a=><option key={a.name}>{a.name}</option>)}</select><select aria-label="Filtrar nivel" value={level} onChange={e=>{setLevel(e.target.value);setPage(0);}}><option value="">Todos los niveles</option><option>INFO</option><option>ERROR</option></select></div><div className="ath-table-scroll"><table><thead><tr><th>Hora de registro</th><th>Nivel</th><th>Agente</th><th>Mensaje</th><th>Detalle</th></tr></thead><tbody>{events.slice(page*20,page*20+20).map(s=><tr key={s.id}><td>{date(s.created_at)}</td><td>{s.status==='completed'?'INFO':'ERROR'}</td><td>{name(s.agent_name)}</td><td>{s.error_message || labels[s.status] || s.status}</td><td><button className="btn btn-ghost btn-sm" onClick={()=>{setSelected(s.id);setTab('steps');}}>Ver intento</button></td></tr>)}</tbody></table></div>{!events.length && <p>Sin registros que coincidan.</p>}<div className="ath-toolbar"><span>{events.length} registros · página {page+1}</span><div><button className="btn btn-ghost btn-sm" disabled={!page} onClick={()=>setPage(p=>p-1)}>Anterior</button><button className="btn btn-ghost btn-sm" disabled={(page+1)*20>=events.length} onClick={()=>setPage(p=>p+1)}>Siguiente</button></div></div></Card>}
      {tab==='metrics' && <div className="ath-columns">{[['Tokens por agente','tokens'],['Tiempo por agente','time']].map(([title,key])=><Card title={title} key={key}>{agents.map(a=><div className="ath-bar-row" key={a.name}><span>{name(a.name)}</span><div className="ath-bar"><span style={{width:`${100*a[key]/Math.max(1,...agents.map(x=>x[key]))}%`,background:agentMeta(a.name)?.color||'var(--brand)'}}/></div><strong>{key==='time'?duration(a.time):num(a.tokens)}</strong><small>{a.steps} intentos · {a.errors} errores</small></div>)}</Card>)}<Card title="Entrada y salida"><p>Tokens de entrada: <strong>{num(run.tokens_in)}</strong></p><p>Tokens de salida: <strong>{num(run.tokens_out)}</strong></p><p>Todos los intentos guardados se incluyen, también los fallidos.</p></Card></div>}
      {tab==='sources' && <Card title={`Fuentes recuperadas (${sources.length})`}><p className="ath-muted">Recuperación RAG registrada; no demuestra que el artículo final cite estas fuentes. No se guardó el texto completo de los fragmentos en estas trazas.</p>{sources.length ? sources.map(s=><article className="ath-source" key={s.doc_id}><h3><FileText size={16}/>{s.title||s.doc_id}</h3><p>{s.authors||'Autoría no registrada'} · Colección: {s.collection||'—'}</p><p>Similitud registrada: {Number(s.score||0).toFixed(2)} · Recuperada por: {(s.used_by||[]).map(name).join(', ')}</p><details><summary>{s.chunk_ids?.length||0} fragmentos registrados · Ver identificadores</summary><Json value={{doc_id:s.doc_id,chunk_ids:s.chunk_ids}}/></details></article>) : <p>No hay fuentes recuperadas registradas para esta ejecución.</p>}</Card>}
      {tab==='integrity' && <Card title="Integridad de los pasos"><p><strong>{({intacta:'Cadena verificada',rota:'Se detectaron inconsistencias',sin_cadena:'Sin hashes para verificar'})[data.integrity.status]||data.integrity.status}</strong></p><p>{data.integrity.verified} pasos verificados · {data.integrity.unchained} sin hash</p><p className="ath-muted">{data.integrity_scope}</p>{data.integrity.issues.length>0 && <Json value={data.integrity.issues}/>}</Card>}
      <p className="ath-footnote">Vista de consulta de datos guardados. No inicia, reanuda ni detiene pipelines. Identificador de ejecución: {run.id}.</p>
    </> }</>}
  </div>;
}
