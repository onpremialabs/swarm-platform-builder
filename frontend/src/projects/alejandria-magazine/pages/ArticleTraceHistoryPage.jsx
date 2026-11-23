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
import { useT } from '../i18n/useT';
import './article-trace-history.css';

const tabs = [['summary','history.tabs.summary',Activity],['steps','history.tabs.steps',Layers],['logs','history.tabs.logs',List],['metrics','history.tabs.metrics',BarChart3],['sources','history.tabs.sources',Database],['integrity','history.tabs.integrity',ShieldCheck]];
const num = n => Number(n || 0).toLocaleString('es-CL');
const duration = ms => { const s = Math.round(Number(ms || 0)/1000); return ms > 0 && ms < 1000 ? `${Math.round(ms)} ms` : s < 60 ? `${s} s` : `${Math.floor(s/60)} min ${s%60} s`; };
const date = value => value ? new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString('es-CL') : '—';
const name = agent => agentMeta(agent)?.label || agent;
const STATUS_KEYS = ['completed', 'failed', 'running', 'cancelled', 'abstained', 'error'];
const statusIcons = {
  completed: CheckCircle, failed: XCircle, running: Clock, cancelled: XCircle, abstained: CircleAlert, error: CircleAlert,
};

function Status({ value }) {
  const { t } = useT();
  const Icon = statusIcons[value] || Info;
  return (
    <span className={`ath-badge ath-${value}`}>
      <Icon size={14} strokeWidth={1.5} aria-hidden="true" />
      {STATUS_KEYS.includes(value) ? t(`history.status.${value}`) : value}
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
  const { t } = useT();
  const statusLabel = value => (STATUS_KEYS.includes(value) ? t(`history.status.${value}`) : value);
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
      .catch(e => { if (!control.signal.aborted) setError(e.response?.status === 403 ? 'history.errorForbidden' : 'history.errorLoad'); });
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
      .catch(() => { if (!control.signal.aborted) setError('history.errorExecution'); })
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
    <Link className="ath-back" to="/dashboard/traceability"><ArrowLeft size={15}/>{t('history.backToTraceability')}</Link>
    <header className="ath-header"><div><p className="ath-eyebrow">{t('history.eyebrow')}</p><h1>{currentHistory?.title || t('history.defaultTitle')}</h1><p>{t('history.subtitle')}</p></div><button className="btn btn-secondary btn-sm" disabled={busy} onClick={()=>setRefresh(n=>n+1)}><RefreshCw size={14}/>{t('history.refresh')}</button></header>
    {error && (
      <div role="alert" className="ath-alert">
        <CircleAlert size={16} aria-hidden="true" />
        <span>{t(error)}</span>
        <button className="btn btn-secondary btn-sm" onClick={() => setRefresh(n => n + 1)}>{t('common.retry')}</button>
      </div>
    )}
    {!currentHistory && !error && <p role="status">{t('history.loading')}</p>}
    {currentHistory && <><div className="ath-toolbar"><label>{t('history.execution')} <select className="input" aria-label={t('history.selectExecution')} value={executionId||''} onChange={e=>setParams({execution:e.target.value})}>{currentHistory.executions.map(e=><option key={e.id} value={e.id}>{t('history.executionOption', { n: e.run_number, date: date(e.started_at), status: statusLabel(e.status) })}</option>)}</select></label><button className="btn btn-secondary btn-sm" disabled={!data} onClick={exportTrace}><Download size={14}/>{t('history.exportJsonl')}</button></div>
    {!currentHistory.executions.length && <Card title={t('history.noTracesTitle')}><p>{t('history.noTraces')}</p></Card>}
    {busy && <p role="status">{t('history.loadingExecution')}</p>}
    {run && <><div className="ath-run-heading"><Status value={run.status}/>{run.recovered_failures>0 && <span>{t('history.recoveredFailures', { count: run.recovered_failures, n: num(run.recovered_failures) })}</span>}<span>{t('history.start', { date: date(run.started_at) })}</span><span>{t('history.lastStep', { date: date(run.last_step_at) })}</span></div>
      <nav className="ath-tabs" aria-label={t('history.sectionsAria')}>{tabs.map(([key,label,Icon])=><button key={key} aria-pressed={tab===key} onClick={()=>setTab(key)}><Icon size={16} strokeWidth={1.5} aria-hidden="true" />{t(label)}</button>)}</nav>
      {tab==='summary' && <><div className="ath-stats">{[['history.stats.attempts',run.steps],['history.stats.tokens',num(run.tokens_in+run.tokens_out)],['history.stats.agentTime',duration(run.latency_ms)],['history.stats.errors',run.failed_steps]].map(([label,value])=><div className="ath-stat" key={label}><span>{t(label)}</span><strong>{value}</strong></div>)}</div><div className="ath-columns"><Card title={t('history.journey')}><div className="ath-timeline">{steps.map(s=><button key={s.id} onClick={()=>{setSelected(s.id);setTab('steps');}}><AgentIcon agent={s.agent_name}/><span><strong>{name(s.agent_name)}</strong><small>{t('history.turn', { n: s.iteration+1, date: date(s.created_at) })}</small></span><span>{duration(s.latency_ms)}</span><Status value={s.status}/></button>)}</div></Card><Card title={t('history.resultTitle')}><p><Status value={run.status}/></p><p>{run.recovered_failures ? t('history.resultRecovered') : t('history.resultLast')}</p>{steps.filter(s=>s.decision).map(s=><div className="ath-decision" key={s.id}><strong>{t('history.decisionHeading', { agent: name(s.agent_name), n: s.iteration+1 })}</strong>{s.decision.score != null && <p>{t('history.reviewerScore')} <strong>{s.decision.score}/100</strong></p>}{s.decision.coherent != null && <p>{t('history.coherence')} <strong>{s.decision.coherent ? t('common.yes') : t('common.no')}</strong></p>}{s.decision.hitl_outcome && <p>{t('history.humanDecision', { outcome: s.decision.hitl_outcome })}</p>}{s.rationale && <details><summary>{t('history.viewRationale')}</summary><p>{s.rationale}</p></details>}<details><summary>{t('history.decisionMetadata')}</summary><Json value={s.decision}/></details></div>)}<p className="ath-muted">{t('history.technicalNote')}</p></Card></div></>}
      {tab==='steps' && <div className="ath-columns"><Card title={t('history.tabs.steps')}><div className="ath-timeline">{steps.map(s=><button key={s.id} aria-pressed={selected===s.id} onClick={()=>setSelected(s.id)}><AgentIcon agent={s.agent_name}/><span><strong>{name(s.agent_name)}</strong><small>{s.model||t('history.modelUnknown')} · {t('history.tokensCount', { n: num(s.tokens_in+s.tokens_out) })}</small></span><Status value={s.status}/></button>)}</div></Card><Card title={trace ? t('history.detailOf', { agent: name(trace.agent_name) }) : t('history.attemptDetail')}>{trace ? <><p><Status value={trace.status}/> · {duration(trace.latency_ms)}</p><p className="ath-muted">
        {t('history.idLabel')} <code>{trace.id}</code><br />
        {t('history.correlation')} {trace.correlation_id ? <code>{trace.correlation_id}</code> : t('history.notRecorded')}
      </p>{trace.error_message && <div className="ath-alert">
        <CircleAlert size={16} aria-hidden="true" />
        <span>{trace.error_message}</span>
      </div>}<details><summary>{t('history.inputParams')}</summary><Json value={{input:trace.input_digest,model:trace.model,params:trace.params}}/></details>{trace.output_text && <details open><summary>{t('history.savedOutput')}</summary><div className="ath-output"><ReactMarkdown>{trace.output_text}</ReactMarkdown></div></details>}<details><summary>{t('history.fullJson')}</summary><Json value={trace}/></details></> : <p>{t('history.selectAttempt')}</p>}</Card></div>}
      {tab === 'logs' && (
        <Card title={t('history.logsTitle')}>
          <p className="ath-muted">{t('history.logsNote')}</p>
          <div className="ath-filters">
            <label className="input-group">
              <span className="input-label">{t('history.searchLogs')}</span>
              <input className="input" type="search" placeholder={t('history.searchPlaceholder')} value={search}
                onChange={e => { setSearch(e.target.value); setPage(0); }} />
            </label>
            <label className="input-group">
              <span className="input-label">{t('history.agent')}</span>
              <select className="input" value={agent} onChange={e => { setAgent(e.target.value); setPage(0); }}>
                <option value="">{t('history.allAgents')}</option>
                {agents.map(a => <option key={a.name} value={a.name}>{name(a.name)}</option>)}
              </select>
            </label>
            <label className="input-group">
              <span className="input-label">{t('history.level')}</span>
              <select className="input" value={level} onChange={e => { setLevel(e.target.value); setPage(0); }}>
                <option value="">{t('history.allLevels')}</option>
                <option>INFO</option>
                <option>ERROR</option>
              </select>
            </label>
          </div>
          {events.length > 0 ? (
            <div className="ath-table-scroll">
              <table>
                <thead><tr>
                  <th scope="col">{t('history.col.time')}</th>
                  <th scope="col">{t('history.col.level')}</th>
                  <th scope="col">{t('history.col.agent')}</th>
                  <th scope="col">{t('history.col.message')}</th>
                  <th scope="col">{t('history.col.detail')}</th>
                </tr></thead>
                <tbody>
                  {events.slice(page * 20, page * 20 + 20).map(s => {
                    const severity = logLevel(s);
                    return (
                      <tr key={s.id}>
                        <td>{date(s.created_at)}</td>
                        <td><span className={`ath-badge ath-${severity.toLowerCase()}`}>{severity}</span></td>
                        <td>{name(s.agent_name)}</td>
                        <td>{s.error_message || statusLabel(s.status)}</td>
                        <td><button className="btn btn-ghost btn-sm"
                          onClick={() => { setSelected(s.id); setTab('steps'); }}>{t('history.viewAttempt')}</button></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : <p>{t('history.noLogs')}</p>}
          <div className="ath-toolbar">
            <span>{t('history.logsPage', { count: events.length, page: page + 1 })}</span>
            <div>
              <button className="btn btn-ghost btn-sm" disabled={!page} onClick={() => setPage(p => p - 1)}>{t('common.previous')}</button>
              <button className="btn btn-ghost btn-sm" disabled={(page + 1) * 20 >= events.length}
                onClick={() => setPage(p => p + 1)}>{t('common.next')}</button>
            </div>
          </div>
        </Card>
      )}
      {tab === 'metrics' && (
        <div className="ath-columns">
          {[['history.tokensByAgent', 'tokens'], ['history.timeByAgent', 'time']].map(([title, key]) => {
            const maximum = Math.max(1, ...agents.map(agent => agent[key]));
            return (
              <Card title={t(title)} key={key}>
                {agents.map(agent => (
                  <div className="ath-bar-row" key={agent.name}>
                    <span>{name(agent.name)}</span>
                    <div className={`ath-bar ath-bar-${key}`} aria-hidden="true">
                      <span style={{ width: `${100 * agent[key] / maximum}%` }} />
                    </div>
                    <strong>{key === 'time' ? duration(agent.time) : num(agent.tokens)}</strong>
                    <small>{t('history.attemptsErrors', { attempts: agent.steps, errors: agent.errors })}</small>
                  </div>
                ))}
              </Card>
            );
          })}
          <Card title={t('history.inOut')}>
            <p>{t('history.tokensIn')} <strong>{num(run.tokens_in)}</strong></p>
            <p>{t('history.tokensOut')} <strong>{num(run.tokens_out)}</strong></p>
            <p>{t('history.allAttempts')}</p>
          </Card>
        </div>
      )}
      {tab==='sources' && <ArticleCitations articleId={id} projectId={projectId} />}
      {tab==='sources' && <Card title={t('history.sourcesTitle', { count: sources.length })}><p className="ath-muted">{t('history.sourcesNote')}</p>{sources.length ? sources.map(s=><article className="ath-source" key={s.doc_id}><h3><FileText size={16}/>{s.title||s.doc_id}</h3><p>{s.authors||t('history.authorsUnknown')} · {t('history.collection', { name: s.collection||'—' })}</p><p>{t('history.similarity', { score: Number(s.score||0).toFixed(2), by: (s.used_by||[]).map(name).join(', ') })}</p><details><summary>{t('history.chunks', { count: s.chunk_ids?.length||0 })}</summary><Json value={{doc_id:s.doc_id,chunk_ids:s.chunk_ids}}/></details></article>) : <p>{t('history.noSources')}</p>}</Card>}
      {tab==='sources' && <Card title={t('history.searchesTitle', { count: searches.length })}><p className="ath-muted">{t('history.searchesNote')}</p>{searches.length ? searches.map(b=><article className="ath-source" key={b.id}><h3><Database size={16}/>{b.query}</h3><p>{t('history.searchMeta', { date: date(b.searched_at), status: b.status, bases: (b.sources||[]).join(', ')||'—' })}</p><p>{t('history.searchCounts', { results: b.result_count, verified: b.verified_count })}{Object.keys(b.discarded||{}).length > 0 && <>{' · '}{t('history.discarded', { list: Object.entries(b.discarded).map(([k,v])=>k + ' ' + v).join(', ') })}</>}</p><details><summary>{t('history.filtersDetail')}</summary><Json value={{filters:b.filters,per_source:b.per_source}}/></details></article>) : <p>{t('history.noSearches')}</p>}</Card>}
      {tab==='integrity' && <Card title={t('history.integrityTitle')}><p>{data.integrity.status === 'intacta'
        ? <span className="ath-badge ath-completed"><ShieldCheck size={14} aria-hidden="true" />{t('history.integrity.intact')}</span>
        : data.integrity.status === 'rota'
          ? <span className="ath-badge ath-error"><CircleAlert size={14} aria-hidden="true" />{t('history.integrity.broken')}</span>
          : <span className="ath-badge"><Info size={14} aria-hidden="true" />{t('history.integrity.none')}</span>}
      </p><p>{t('history.integrityCounts', { verified: data.integrity.verified, unchained: data.integrity.unchained })}</p><p className="ath-muted">{data.integrity_scope}</p>{data.integrity.issues.length>0 && <Json value={data.integrity.issues}/>}</Card>}
      <p className="ath-footnote">{t('history.footnote')} <code>{run.id}</code>.</p>
    </> }</>}
  </div>;
}
