"use client";

import {useState} from "react";
import {api,dateAt,dateTimeAt,messageFor,shortId} from "@/lib/api";
import {useSession} from "@/lib/session";
import {useWorkspaceEvidence} from "@/lib/use-workspace";
import {DataState} from "@/components/data-state";
import {StatusBadge} from "@/components/status-badge";
import type {PlanResult,PlanningSession} from "@/lib/types";

function asRecord(value:unknown):Record<string,unknown>|null{return value&&typeof value==="object"&&!Array.isArray(value)?value as Record<string,unknown>:null}
function metric(value:unknown,unit=""){return typeof value==="number"&&Number.isFinite(value)?`${value}${unit}`:"Unavailable"}
function stage(name:string,value:string|number|null|undefined,detail?:string){
  return <div className="pipeline-stage" key={name}><span className="pipeline-marker" aria-hidden="true"/><div><strong>{name}</strong>{detail&&<small>{detail}</small>}</div>
    {typeof value==="number"?<strong className="stage-number">{value}</strong>:<StatusBadge value={value??"NOT_RECORDED"}/>}</div>;
}
function SolverMetrics({result}:{result:PlanResult|null}){
  if(!result)return <DataState title="Solver result not recorded" detail="The saved run has not published a result. Refresh after the durable worker completes."/>;
  const terms=asRecord(result.objective_terms);
  return <div className="solver-body"><div className="solver-metrics">
    <div><span>Solver status</span><StatusBadge value={result.solver_status??"NOT_RECORDED"}/></div>
    <div><span>Incumbent</span><strong>{result.has_incumbent===true?"Yes":result.has_incumbent===false?"No":"Unavailable"}</strong></div>
    <div><span>Objective</span><strong>{metric(result.objective_value)}</strong></div>
    <div><span>Best bound</span><strong>{metric(result.best_bound)}</strong></div>
    <div><span>Runtime</span><strong>{metric(result.wall_time_seconds," s")}</strong></div>
    <div><span>Branches</span><strong>{metric(result.branches)}</strong></div>
    <div><span>Conflicts</span><strong>{metric(result.conflicts)}</strong></div>
    <div><span>Optimality scope</span><strong>{typeof result.optimality_scope==="string"?result.optimality_scope.replaceAll("_"," "):"Not recorded"}</strong></div>
  </div>
    {result.has_incumbent===false&&<div className="inline-alert">No incumbent assignment was returned. Solver status and diagnostics are shown exactly as saved; no fallback schedule is fabricated.</div>}
    {terms&&<div className="solver-terms"><h3>Configured objective terms</h3><div className="solver-term-head"><span>Term</span><span>Raw</span><span>Weight</span><span>Weighted</span></div>
      {Object.entries(terms).map(([name,raw])=>{const row=asRecord(raw);return <div className="solver-term-row" key={name}><strong>{name.replaceAll("_"," ")}</strong><span>{metric(row?.raw)}</span><span>{metric(row?.weight)}</span><span>{metric(row?.weighted)}</span></div>})}</div>}
    {result.counts&&<div className="solver-counts">{Object.entries(result.counts).map(([name,value])=><div key={name}><span>{name.replaceAll("_"," ")}</span><strong>{value}</strong></div>)}</div>}
    {Array.isArray(result.review_blockers)&&result.review_blockers.length>0&&<div className="inline-alert">Review blockers: {result.review_blockers.map(String).join(" · ")}</div>}
  </div>;
}
export default function OptimizationPage(){
  const data=useWorkspaceEvidence();
  const {value:user}=useSession();
  const [busy,setBusy]=useState(false),[actionError,setActionError]=useState<string|null>(null),[message,setMessage]=useState<string|null>(null);
  const session=data.session;
  const baseline=session?.runs.find(x=>x.planner_type==="BASELINE");
  const optimized=session?.runs.find(x=>x.planner_type==="CP_SAT");
  const artifacts=session?.artifacts;
  const result=data.view?.selected_run?.result??null;
  const canStart=!!data.snapshot&&data.view?.source_state==="CURRENT"&&!data.snapshot.scenario_id&&["PLANNER","ADMIN"].includes(user?.user.role??"");
  async function start(){if(!data.snapshot||!user)return;setBusy(true);setActionError(null);setMessage(null);
    try{const next=await api<PlanningSession>("/planning-sessions",{method:"POST",csrf:user.csrf_token,
      body:{idempotency_key:crypto.randomUUID(),snapshot_id:data.snapshot.id,expected_snapshot_hash:data.snapshot.content_hash}});
      data.selectSession(next.id);data.refresh();setMessage(`Planning session ${shortId(next.id)} queued; worker state will update from the API.`);
    }catch(cause){setActionError(messageFor(cause))}finally{setBusy(false)}
  }
  return <div className="content-flow optimization-page"><div className="page-heading"><div><span className="eyebrow">DURABLE PLANNING SESSION</span><h1>Optimization state</h1>
    <p>Recorded preparation, baseline and CP-SAT outcomes—without inferred progress or invented solver values.</p></div>
    <div className="page-actions"><button className="button button-outline" onClick={data.refresh}>Refresh state</button><button className="button button-primary" disabled={!canStart||busy}
      onClick={()=>void start()}>{busy?"Queuing…":"Start planning session"}</button></div></div>
    {(data.error||actionError)&&<div className="inline-alert" role="alert">{data.error??actionError}</div>}{message&&<div className="inline-success" role="status">{message}</div>}
    <div className="planning-context panel"><label className="field">Planning snapshot<select value={data.selection.snapshotId??""} onChange={e=>data.selectSnapshot(e.target.value||null)}>
      <option value="">Select a saved snapshot</option>{data.snapshots.map(x=><option key={x.id} value={x.id}>{x.source_scope} · {dateAt(x.horizon_start)} · {shortId(x.id)}</option>)}</select></label>
      <label className="field">Planning session<select value={data.selection.sessionId??""} disabled={!data.snapshot} onChange={e=>data.selectSession(e.target.value||null)}><option value="">No session selected</option>
        {data.sessions.map(x=><option key={x.id} value={x.id}>{dateTimeAt(x.created_at)} · {x.status} · {shortId(x.id)}</option>)}</select></label>
      <label className="field">Inspect run<select value={data.runId??""} disabled={!data.snapshot||!!data.selection.revisionId} onChange={e=>data.selectRun(e.target.value||null)}><option value="">No run selected</option>
        {data.runs.map(x=><option key={x.id} value={x.id}>{x.planner_type} · {x.job_status} · {shortId(x.id)}</option>)}</select></label>
      <div className="context-stamp"><span>Source state</span><strong>{data.view?.source_state??"NOT SELECTED"}</strong><small>{data.snapshot?.source_scope??"Choose a snapshot"}</small></div></div>
    {data.view?.current_blockers.length?<div className="inline-alert">Current blockers: {data.view.current_blockers.join(" · ").replaceAll("_"," ")}. Historical run metrics remain visible; review requires current validation.</div>:null}
    {data.loading||data.viewLoading&&!data.view?<div className="panel"><DataState title="Loading planning session" detail="Reading saved worker and solver artifacts…"/></div>:
    !data.snapshot?<div className="panel"><DataState title="Select a planning snapshot" detail="A saved snapshot is required to start or inspect a session."/></div>:
    <div className="optimization-layout"><section className="panel"><div className="panel-header"><div><h2>Recorded pipeline</h2><p>{session?`Session ${shortId(session.id)} · ${dateTimeAt(session.created_at)}`:"Choose a saved session or start one"}</p></div>
      <StatusBadge value={session?.status??"NOT_STARTED"}/></div>
      {session?<div className="pipeline-list">
        {stage("Snapshot bound","RECORDED",shortId(session.snapshot_id))}
        {stage("Preparation",session.preparation_status)}
        {stage("Rule priority",typeof artifacts?.priority_count==="number"?artifacts.priority_count:null,"assessments recorded")}
        {stage("Corridor availability",artifacts?.availability_ids?.length??null,"calculation artifacts")}
        {stage("Maintenance opportunities",artifacts?.opportunity_id?"RECORDED":"NOT_RECORDED",artifacts?.opportunity_id?shortId(artifacts.opportunity_id):undefined)}
        {stage("Coordination & resources",artifacts?.coordination_id?"RECORDED":"NOT_RECORDED",artifacts?.coordination_id?shortId(artifacts.coordination_id):undefined)}
        {stage("First-feasible baseline",baseline?.status??"NOT_QUEUED",baseline?.id?shortId(baseline.id):undefined)}
        {stage("CP-SAT optimization",optimized?.status??"NOT_QUEUED",optimized?.solver_status??undefined)}
        {stage("Saved proposal",data.view?.selected_revision?"RECORDED":"NOT_SELECTED")}
        {stage("Independent validation",data.view?.validation?.status??"NOT_RUN")}
      </div>:<DataState title="No session selected" detail="Select an existing session or start a new one. No stage is marked complete until its backend artifact is present."/>}
      {session?.error&&<div className="panel-body inline-alert">{session.error.code??"SESSION_FAILED"}: {session.error.detail??"No detail recorded"}</div>}
      {session&&!['COMPLETED','FAILED','SUPERSEDED'].includes(session.status)&&<div className="panel-body inline-note">Durable worker state is being polled. Completion and elapsed time are never inferred.</div>}
    </section><section className="panel"><div className="panel-header"><div><h2>Saved solver metrics</h2><p>{data.view?.selected_run?`${data.view.selected_run.planner_type} · ${shortId(data.view.selected_run.id)}`:"Select a completed baseline or CP-SAT run"}</p></div>
      <StatusBadge value={data.view?.selected_run?.result?.solver_status??data.view?.selected_run?.status??"NOT_SELECTED"}/></div>
      <SolverMetrics result={result}/></section></div>}
    <p className="planning-disclaimer">Optimality, when reported, is limited to the generated candidate set. A run result is a software proposal; independent validation and controller review are separate gates.</p>
  </div>;
}
