"use client";

import {useCallback, useEffect, useState} from "react";
import Link from "next/link";
import {SnapshotPreparation} from "@/components/snapshot-preparation";
import {LiveMaintenanceIntake} from "@/components/live-maintenance-intake";
import {RailIcon} from "@/components/rail-icon";
import {TaskStages} from "@/components/task-stages";
import {api, ApiError, dateAt, dateTimeAt, messageFor, shortId, timeAt} from "@/lib/api";
import {useSession} from "@/lib/session";
import {useCase} from "@/components/app-shell";
import {DataState} from "@/components/data-state";
import {DepartmentBadge, StatusBadge} from "@/components/status-badge";
import {timelineItems} from "@/lib/timeline";
import type {Focus} from "@/lib/timeline";
import {TimeTrackTimeline} from "@/components/time-track-timeline";
import {CorridorOverviewHeader} from "@/components/corridor-overview-header";
import {CorridorSchematic} from "@/components/corridor-schematic";
import {SelectedBlockInspector} from "@/components/selected-block-inspector";
import {PlanComparisonCard} from "@/components/plan-comparison-card";
import type {Candidate, Page, PlanningSession, RunIndexItem, SnapshotSummary, WorkspaceView} from "@/lib/types";
function Detail({label,children}:{label:string;children:React.ReactNode}){return <div className="evidence-detail"><span>{label}</span><strong>{children}</strong></div>}
function CandidateDetails({candidate}:{candidate:Candidate}){return <>
  <Detail label="Possession">{dateTimeAt(candidate.possession_start)} – {timeAt(candidate.possession_end)} IST</Detail>
  <Detail label="Track footprint">{candidate.track_ids.join(", ")}</Detail>
  <Detail label="Mode">{candidate.mode.replaceAll("_"," ")}</Detail>
  <Detail label="Included work">{candidate.request_ids.map(shortId).join(", ")}</Detail>
  <div className="evidence-subhead">Setup · work · restoration</div>
  <TaskStages candidate={candidate}/>
  <div className="evidence-subhead">Concrete resources</div>
  {candidate.allocations.length?candidate.allocations.map((a,index)=><div key={`${a.resource_id}:${index}`} className="resource-line"><strong>{a.resource_id}</strong><span>{a.resource_type} · {timeAt(a.start_at)}–{timeAt(a.end_at)}</span></div>):<p className="muted">No resource allocation recorded.</p>}
  {!!candidate.rule_ids.length&&<Detail label="Compatibility rules">{candidate.rule_ids.join(", ")}</Detail>}
</>}
function EvidenceInspector({view,focus}:{view:WorkspaceView;focus:Focus|null}){
  const demand=focus?.kind==="request"?view.demands.find(d=>d.request_id===focus.id):undefined;
  const item=timelineItems(view).find(x=>x.kind===focus?.kind&&x.id===focus?.id);
  const candidate=focus?.kind==="candidate"?view.coordination?.result.candidates.find(x=>x.id===focus.id):
    focus?.kind==="assignment"?(view.selected_revision?.content??view.selected_run?.result)?.assignments?.find(x=>x.id===focus.id):undefined;
  return <aside className="panel evidence-panel" aria-label="Evidence inspector"><div className="panel-header"><div><h2>Evidence inspector</h2><p>Source facts, derived windows and proposal context</p></div></div>
    {!focus?<DataState title="Select timeline evidence" detail="Choose a demand, train, window or proposed block to inspect its saved evidence."/>:
    <div className="evidence-body"><div className="inspector-title"><span className="eyebrow">{focus.kind.replaceAll("_"," ")}</span><h3>{demand?.request.issue_type??item?.label??shortId(focus.id)}</h3><span className="mono muted" title={focus.id}>{shortId(focus.id)}</span></div>
      {demand?<><div className="inspector-badges"><DepartmentBadge department={demand.request.department}/><StatusBadge value={demand.readiness.status}/></div>
        <Detail label="Asset / track">{demand.request.asset_id} · {demand.request.footprint.join(", ")}</Detail>
        <Detail label="Earliest / deadline">{dateTimeAt(demand.request.earliest_at)}<br/>{dateTimeAt(demand.request.deadline_at)}</Detail>
        <Detail label="Setup / work / handback">{demand.request.setup_minutes} / {demand.request.work_minutes} / {demand.request.restore_minutes} min</Detail>
        <Detail label="Line / power / S&T">{demand.access_requirements.line_block} / {demand.access_requirements.power_block} / {demand.access_requirements.snt_disconnection}</Detail>
        <Detail label="Isolation zone">{demand.access_requirements.electrical_isolation_zone??"Not declared"}</Detail>
        <Detail label="Access provision">{demand.access_requirements.provision_status.replaceAll("_"," ")}</Detail>
        <Detail label="Priority">{demand.priority?`${demand.priority.method} · ${(demand.priority.score_basis_points/100).toFixed(1)}/100 · ${demand.priority.priority_band}`:"Not assessed"}</Detail>
        {demand.priority&&<div className="contributions">{Object.entries(demand.priority.contributions).map(([key,value])=><div key={key}><span>{key.replaceAll("_"," ")}</span><strong>{value}</strong></div>)}</div>}
        <Detail label="Scheduling outcome">{demand.scheduling_outcome.replaceAll("_"," ")}</Detail>
        <Detail label="Candidate / selected">{demand.readiness.candidate_ids.length} / {demand.readiness.selected_candidate_ids.length}</Detail>
        {!!demand.readiness.reasons.length&&<div className="reason-box"><strong>Readiness evidence</strong>{demand.readiness.reasons.map(x=><span key={x}>{x.replaceAll("_"," ")}</span>)}</div>}
        {demand.deferred_evidence&&<div className="reason-box"><strong>Deferral evidence</strong><span>{JSON.stringify(demand.deferred_evidence)}</span></div>}
        <p className="quiet-note">Readiness describes the selected planning context. It is not operating authorization.</p></>:
      candidate?<CandidateDetails candidate={candidate}/>:
      item?<><Detail label="Track">{item.track}</Detail><Detail label="Interval">{dateTimeAt(item.start)} – {timeAt(item.end)} IST</Detail>
        {focus.kind==="train"&&<Detail label="Evidence">Confirmed section occupancy from the saved snapshot</Detail>}
        {focus.kind==="freight"&&<Detail label="Evidence">Forecast envelope; uncertainty remains visible</Detail>}
        {focus.kind==="coa"&&<Detail label="Evidence">COA declaration, not an issued possession</Detail>}
        {focus.kind==="window"&&<Detail label="Evidence">Calculated availability; inspect exclusions before scheduling</Detail>}</>:<p className="muted">Selected evidence is no longer in this view. Refresh the workspace.</p>}
    </div>}
  </aside>;
}
export default function PlanningPage(){
  const [inspectorTab,setInspectorTab]=useState<"block"|"demand"|"evidence">("block");
  const [demandQuery,setDemandQuery]=useState("");
  const [department,setDepartment]=useState("ALL");
  const {value:session,invalidate}=useSession();const selectedCase=useCase();
  const [snapshots,setSnapshots]=useState<SnapshotSummary[]>([]),[runs,setRuns]=useState<RunIndexItem[]>([]),[sessions,setSessions]=useState<PlanningSession[]>([]);
  const [workspace,setWorkspace]=useState<WorkspaceView|null>(null),[focus,setFocus]=useState<Focus|null>(null);
  const [runId,setRunId]=useState<string|null>(null),[loading,setLoading]=useState(true),[workspaceLoading,setWorkspaceLoading]=useState(false),[busy,setBusy]=useState(false);
  const [error,setError]=useState<string|null>(null),[actionMessage,setActionMessage]=useState<string|null>(null),[refreshKey,setRefreshKey]=useState(0);
  const chosen=snapshots.find(x=>x.id===selectedCase.snapshotId);
  const chosenSession=sessions.find(x=>x.id===selectedCase.sessionId);
  const effectiveRunId=selectedCase.revisionId?null:runId;
  const reload=useCallback(()=>setRefreshKey(x=>x+1),[]);
  useEffect(()=>{let cancelled=false;setLoading(true);setError(null);
    void api<Page<SnapshotSummary>>("/workspace/snapshots?scenario=ANY&limit=100").then(page=>{
      if(cancelled)return;setSnapshots(page.items);
      if(selectedCase.snapshotId&&!page.items.some(x=>x.id===selectedCase.snapshotId)) selectedCase.selectSnapshot(null);
    }).catch(cause=>{if(cancelled)return;if(cause instanceof ApiError&&cause.status===401)invalidate();setError(messageFor(cause));}).finally(()=>{if(!cancelled)setLoading(false)});
    return()=>{cancelled=true};
  // Snapshot selection is retained in sessionStorage; this catalog refreshes only on explicit refresh.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[refreshKey,invalidate]);
  useEffect(()=>{if(!selectedCase.snapshotId){setWorkspace(null);setRuns([]);setSessions([]);return}
    const controller=new AbortController();const id=encodeURIComponent(selectedCase.snapshotId);
    void Promise.all([api<Page<RunIndexItem>>(`/workspace/runs?snapshot_id=${id}&limit=100`,{signal:controller.signal}),
      api<Page<PlanningSession>>(`/workspace/planning-sessions?snapshot_id=${id}&limit=100`,{signal:controller.signal})]).then(([r,s])=>{setRuns(r.items);setSessions(s.items)}).catch(cause=>{if(!controller.signal.aborted)setError(messageFor(cause))});
    return()=>controller.abort();
  },[selectedCase.snapshotId,refreshKey]);
  useEffect(()=>{if(!selectedCase.snapshotId||!selectedCase.sessionId)return;
    const current=sessions.find(x=>x.id===selectedCase.sessionId);if(!current||["COMPLETED","FAILED","SUPERSEDED"].includes(current.status))return;
    const timer=setTimeout(()=>{void api<PlanningSession>(`/planning-sessions/${selectedCase.sessionId}`).then(next=>{
      setSessions(previous=>previous.map(x=>x.id===next.id?next:x));
      if(next.status==="COMPLETED")reload();
    }).catch(cause=>setError(messageFor(cause)))},2500);
    return()=>clearTimeout(timer);
  },[sessions,selectedCase.sessionId,selectedCase.snapshotId,reload]);
  useEffect(()=>{if(!selectedCase.snapshotId){setWorkspace(null);return}const controller=new AbortController();setWorkspaceLoading(true);setError(null);
    const suffix=selectedCase.revisionId?`?plan_revision_id=${encodeURIComponent(selectedCase.revisionId)}`:effectiveRunId?`?run_id=${encodeURIComponent(effectiveRunId)}`:"";
    void api<WorkspaceView>(`/snapshots/${selectedCase.snapshotId}/workspace${suffix}`,{signal:controller.signal}).then(value=>{setWorkspace(value);setFocus(null)})
      .catch(cause=>{if(!controller.signal.aborted){setWorkspace(null);setError(messageFor(cause))}})
      .finally(()=>{if(!controller.signal.aborted)setWorkspaceLoading(false)});
    return()=>controller.abort();
  },[selectedCase.snapshotId,selectedCase.revisionId,effectiveRunId,refreshKey]);
  async function perform(label:string, action:()=>Promise<void>){setBusy(true);setError(null);setActionMessage(null);try{await action();setActionMessage(label);reload()}catch(cause){setError(messageFor(cause))}finally{setBusy(false)}}
  const canPlan=["ADMIN","PLANNER"].includes(session?.user.role??"");
  const optimized=chosenSession?.runs.find(x=>x.planner_type==="CP_SAT");
  const selectedRunSummary=selectedCase.revisionId
    ?runs.find(x=>x.revision_ids.includes(selectedCase.revisionId!))
    :runs.find(x=>x.id===runId);
  const snapshotBaseline=runs.find(x=>x.planner_type==="BASELINE");
  const snapshotOptimized=selectedRunSummary?.planner_type==="CP_SAT"?selectedRunSummary:runs.find(x=>x.planner_type==="CP_SAT");
  const baselineStatus=chosenSession
    ?chosenSession.runs.find(x=>x.planner_type==="BASELINE")?.status??"Not run in this session"
    :snapshotBaseline?.job_status??"No saved run";
  const solverStatus=chosenSession
    ?optimized?.solver_status??optimized?.status??"Not run in this session"
    :(workspace?.selected_run?.planner_type==="CP_SAT"?workspace.selected_run.result?.solver_status:null)??snapshotOptimized?.solver_status??snapshotOptimized?.job_status??"No saved run";
  const sessionStatus=chosenSession?.status??(sessions.length?"NO_SESSION_SELECTED":"NO_SESSION_RECORDED");
  const preparationStatus=chosenSession?.preparation_status??(sessions.length?"No session selected":"No session recorded");
  const canMaterialize=!!optimized&&optimized.status==="COMPLETED"&&optimized.has_incumbent&&!!optimized.result_hash&&!selectedCase.revisionId;
  const plan=workspace?.selected_revision?.content??workspace?.selected_run?.result;
  const sourceBlocked=workspace?.source_state!=="CURRENT";
  const visibleDemands=workspace?.demands.filter(d=>(department==="ALL"||d.request.department===department)&&`${d.request_id} ${d.request.issue_type} ${d.request.asset_id} ${d.request.footprint.join(" ")}`.toLowerCase().includes(demandQuery.toLowerCase()))??[];
  function inspect(next:Focus){setFocus(next);setInspectorTab("evidence")}
  return <div className="content-flow planning-page"><div className="page-heading"><div><span className="eyebrow">INTEGRATED BLOCK PLANNING</span><h1>Planning Workspace</h1><p>Integrated view of train movements, maintenance demand, railway capacity and proposed blocks.</p></div>
    <div className="page-actions"><button className="button button-outline" onClick={reload} disabled={busy}><RailIcon name="report" size={14} /> Refresh evidence</button>
      <button className="button button-primary button-generate" disabled={!canPlan||!chosen||sourceBlocked||busy||!!chosen.scenario_id} title={chosen?.scenario_id?"Scenarios use the isolated what-if workflow":undefined}
        onClick={()=>void perform("Planning session queued. Worker progress is shown below.",async()=>{
          const next=await api<PlanningSession>("/planning-sessions",{method:"POST",csrf:session!.csrf_token,body:{idempotency_key:crypto.randomUUID(),snapshot_id:chosen!.id,expected_snapshot_hash:chosen!.content_hash}});
          selectedCase.selectSession(next.id);setSessions(previous=>[next,...previous]);setRunId(null);
        })}>+ Generate Optimized Plan</button></div></div>
    {error&&<div className="inline-alert" role="alert">{error}</div>}{actionMessage&&<div className="inline-success" role="status">{actionMessage}</div>}
    <div className="planning-context panel"><label className="field">Planning snapshot<select value={selectedCase.snapshotId??""} onChange={e=>{selectedCase.selectSnapshot(e.target.value||null);setRunId(null)}}>
      <option value="">Select a saved corridor snapshot</option>{snapshots.map(x=>{
        const isNCR = x.track_ids.some(t => t.includes("DER") || t.includes("KRJ") || t.includes("GZB") || t.includes("ALJN"));
        const label = isNCR ? `🚆 NCR Trunk Corridor (GZB–ALJN)` : x.track_ids.join(", ");
        return <option key={x.id} value={x.id}>{label} · {dateAt(x.horizon_start)} · Ref: {shortId(x.id)}</option>;
      })}</select></label>
      <label className="field">Planning session<select value={selectedCase.sessionId??""} disabled={!chosen} onChange={e=>{selectedCase.selectSession(e.target.value||null);setRunId(null)}}><option value="">Snapshot facts only</option>
        {sessions.map(x=><option key={x.id} value={x.id}>{dateTimeAt(x.created_at)} · {x.status} · {shortId(x.id)}</option>)}</select></label>
      <label className="field">Plan evidence<select value={selectedCase.revisionId?`revision:${selectedCase.revisionId}`:runId?`run:${runId}`:""} disabled={!chosen} onChange={e=>{
        const value=e.target.value;if(value.startsWith("revision:")){selectedCase.selectRevision(value.slice(9));setRunId(null)}else{selectedCase.selectRevision(null);setRunId(value.startsWith("run:")?value.slice(4):null)}
      }}><option value="">No plan selected</option>{runs.flatMap(x=>[
        <option key={`run:${x.id}`} value={`run:${x.id}`}>{x.planner_type==="CP_SAT"?"✨ AI Shadow Plan (CP-SAT)":"⏱️ Baseline Plan"} · {x.job_status} · {shortId(x.id)}</option>,
        ...x.revision_ids.map(id=><option key={`revision:${id}`} value={`revision:${id}`}>Saved Proposal · {x.planner_type==="CP_SAT"?"✨ AI Plan":"⏱️ Baseline"} · {shortId(id)}</option>)])}</select></label>
      <div className="context-stamp"><span>Current evidence</span><strong>{chosen?.source_scope??"NONE"}</strong><small>{chosen?`${dateTimeAt(chosen.horizon_start)} – ${dateTimeAt(chosen.horizon_end)}`:"Choose a snapshot"}</small></div></div>

    {workspace && (
      <>
        <CorridorOverviewHeader view={workspace} />
        <CorridorSchematic view={workspace} />
      </>
    )}

    <SnapshotPreparation defaults={chosen?{horizon_start:chosen.horizon_start,horizon_end:chosen.horizon_end,track_ids:chosen.track_ids}:undefined} onSaved={snapshot=>{setSnapshots(previous=>[snapshot,...previous.filter(item=>item.id!==snapshot.id)]);selectedCase.selectSnapshot(snapshot.id);setRunId(null);reload();}}/>
    <LiveMaintenanceIntake captured={workspace?.demands.map(item=>({id:item.request_id,revision:item.revision}))??[]}/>
    {loading?<div className="panel"><DataState title="Loading snapshots" detail="Reading saved planning contexts from the backend…"/></div>:
    !chosen?<div className="panel"><DataState title={snapshots.length?"Select a planning snapshot":"No snapshots available"} detail={snapshots.length?"Choose a snapshot to inspect recorded occupancy and maintenance demand.":"Create a snapshot through the backend planning flow before using this workspace."}/></div>:
    workspaceLoading&&!workspace?<div className="panel"><DataState title="Loading planning evidence" detail="Reading source facts, generated artifacts and current blockers…"/></div>:
    workspace?<>
      {workspace.current_blockers.length>0&&<div className="inline-alert" role="status"><strong>Source or review blocked:</strong> {workspace.current_blockers.join(" · ").replaceAll("_"," ")}. Recheck facts before starting or approving a plan.</div>}
      <div className="planning-status"><div><span>Snapshot</span><strong className="mono">{shortId(chosen.id)}</strong></div><div><span>Source state</span><StatusBadge value={workspace.source_state}/></div>
        <div><span>Session</span><StatusBadge value={sessionStatus}/></div><div><span>Solver</span><StatusBadge value={solverStatus}/></div>
        <div><span>Independent validation</span><StatusBadge value={workspace.validation?.status??"NOT_RUN"}/></div><div><span>Authority</span><strong>Software proposal</strong></div></div>
      <div className="planning-grid">
        <div className="planning-rail-tabs segmented-control" aria-label="Planning side panel">
          <button type="button" aria-pressed={inspectorTab==="block"} onClick={()=>setInspectorTab("block")}><RailIcon name="corridor" size={16}/>Selected block</button>
          <button type="button" aria-pressed={inspectorTab==="demand"} onClick={()=>setInspectorTab("demand")}><RailIcon name="work" size={16}/>Work queue <span>{workspace.demands.length}</span></button>
          <button type="button" aria-pressed={inspectorTab==="evidence"} onClick={()=>setInspectorTab("evidence")}><RailIcon name="search" size={16}/>Evidence</button>
        </div>
        {inspectorTab==="block"&&<SelectedBlockInspector view={workspace} focus={focus} onInspect={inspect}/>}
        {inspectorTab==="demand"&&<section className="panel demand-panel"><div className="panel-header"><div><h2>Maintenance demand</h2><p>{visibleDemands.length} of {workspace.demands.length} requests · {workspace.demands.filter(d=>d.request.mandatory).length} mandatory</p></div></div>
        <div className="demand-filters"><label className="field"><span className="sr-only">Search work queue</span><input type="search" placeholder="Find work, asset or track…" value={demandQuery} onChange={event=>setDemandQuery(event.target.value)}/></label><label className="field"><span className="sr-only">Department</span><select value={department} onChange={event=>setDepartment(event.target.value)}><option value="ALL">All departments</option><option value="ENGINEERING">Engineering</option><option value="TRD">TRD</option><option value="SNT">S&amp;T</option></select></label></div>
        {workspace.demands.length===0?<DataState title="No requests in snapshot" detail="No maintenance demand was captured for this planning horizon."/>:visibleDemands.length===0?<DataState title="No matching demand" detail="Try another asset, track or department."/>:<div className="demand-list">{visibleDemands.map(d=><button key={d.request_id} type="button"
          className={`demand-card department-border-${d.request.department.toLowerCase()} ${focus?.kind==="request"&&focus.id===d.request_id?"demand-card-active":""}`} onClick={()=>inspect({kind:"request",id:d.request_id})}>
          <span className="demand-card-top"><DepartmentBadge department={d.request.department}/><span className="mono">{shortId(d.request_id)}</span></span>
          <strong>{d.request.issue_type}</strong><span>{d.request.asset_id} · {d.request.footprint.join(", ")}</span>
          <span className="demand-card-meta">{d.request.work_minutes} min work · due {dateAt(d.request.deadline_at)}</span>
          <span className="demand-card-bottom"><StatusBadge value={d.readiness.status}/>{d.priority?<span>{d.priority.priority_band} · {(d.priority.score_basis_points/100).toFixed(1)}</span>:<span>Priority not assessed</span>}</span>
          <span className="demand-card-bottom"><span>Line {d.access_requirements.line_block}</span><span>Power {d.access_requirements.power_block}</span></span>
        </button>)}</div>}</section>}
        <div className="planning-center">
          <TimeTrackTimeline view={workspace} focus={focus} onFocus={inspect}/>
          <PlanComparisonCard view={workspace} />
          <section className="panel session-panel"><div className="panel-header"><div><h2>Planning session and proposal</h2><p>Saved worker and solver evidence</p></div></div>
            <div className="session-content"><div className="session-metrics"><div><span>Preparation</span><strong>{preparationStatus}</strong></div>
              <div><span>Baseline</span><strong>{baselineStatus}</strong></div>
              <div><span>CP-SAT</span><strong>{solverStatus}</strong></div>
              <div><span>Candidates</span><strong>{workspace.coordination?.result.counts?.candidates??workspace.coordination?.result.candidates.length??"Not generated"}</strong></div>
              <div><span>Assignments</span><strong>{plan?.assignments?.length??"No plan selected"}</strong></div>
              <div><span>Validation</span><strong>{workspace.validation?.status??"Not run"}</strong></div></div>
              {!chosenSession&&(snapshotBaseline||snapshotOptimized)&&<div className="inline-note">Saved run statuses belong to this snapshot. {sessions.length?"Select a planning session to inspect paired stage evidence.":"No paired planning session is recorded for these runs."}</div>}
              {chosenSession?.error&&<div className="inline-alert">{chosenSession.error.code??"Session failed"}: {chosenSession.error.detail??"Inspect backend logs."}</div>}
              {plan?.deferred?.length?<div className="deferred-list"><strong>Deferred requests</strong>{plan.deferred.map(x=><div key={x.request_id}><span className="mono">{shortId(x.request_id)}</span><span>{x.reason}</span></div>)}</div>:null}
              {chosenSession&&!["COMPLETED","FAILED","SUPERSEDED"].includes(chosenSession.status)&&<div className="inline-note">The durable worker has not finished. This view refreshes the recorded state; no completion is assumed.</div>}
              <div className="session-actions"><button className="button button-outline" disabled={!canMaterialize||busy||sourceBlocked} onClick={()=>void perform("Saved proposal created.",async()=>{
                const revision=await api<{id:string}>("/plan-revisions",{method:"POST",csrf:session!.csrf_token,body:{run_id:optimized!.id,expected_plan_hash:optimized!.result_hash}});
                selectedCase.selectRevision(revision.id);setRunId(null);
              })}>Save optimized proposal</button>
              <button className="button button-outline" disabled={!workspace.selected_revision||busy||!canPlan} onClick={()=>void perform("Independent validator ran; inspect its actual status above.",async()=>{
                await api("/validation-reports",{method:"POST",csrf:session!.csrf_token,body:{plan_revision_id:workspace.selected_revision!.id,expected_plan_hash:workspace.selected_revision!.plan_hash}});
              })}>Run independent validation</button><Link className="session-next-link" href="/review">Controller review <RailIcon name="arrow" size={16}/></Link></div>
            </div></section></div>
        {inspectorTab==="evidence"&&<EvidenceInspector view={workspace} focus={focus}/>}</div>
      <p className="planning-disclaimer">All visible intervals belong to snapshot <span className="mono">{shortId(chosen.id)}</span>. Validation PASS means compliance with configured prototype constraints. Operational possession authority remains external to RailSync.</p>
    </>:null}
  </div>;
}
