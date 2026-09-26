"use client";

import {useEffect,useState} from "react";
import {api,ApiError,dateAt,dateTimeAt,messageFor,shortId,timeAt} from "@/lib/api";
import {useSession} from "@/lib/session";
import {useWorkspaceEvidence} from "@/lib/use-workspace";
import {DataState} from "@/components/data-state";
import {StatusBadge} from "@/components/status-badge";
import {TimeTrackTimeline} from "@/components/time-track-timeline";
import {comparisonMatchesRuns} from "@/lib/saved-comparison";
import type {Focus} from "@/lib/timeline";
import type {ComparisonMetric,PlanComparison,PlanningRun,ReportArtifactIndex,WorkspaceView} from "@/lib/types";

const featured=["requests_scheduled","mandatory_coverage_basis_points","possession_count","reserved_track_minutes","forecast_exposure_train_track_seconds"];
const labels:Record<string,string>={requests_scheduled:"Requests scheduled",critical_requests_scheduled:"Critical requests scheduled",possession_count:"Possessions",reserved_track_minutes:"Reserved track time",task_work_minutes:"Task work",block_utilization_basis_points:"Block utilization",mandatory_coverage_basis_points:"Mandatory coverage",on_time_coverage_basis_points:"On-time coverage",maintenance_track_availability_basis_points:"Planned track availability",forecast_exposure_train_track_seconds:"Forecast freight exposure",multi_request_possessions:"Multi-request possessions",bundled_extra_tasks:"Additional bundled tasks",measured_train_delay_minutes:"Measured train delay",solver_wall_time_seconds:"Solver runtime"};
const measures=new Intl.NumberFormat("en-IN",{maximumFractionDigits:1});
function value(number:number|null,unit:string){
  if(number===null||!Number.isFinite(number))return "N/A";
  if(unit==="basis_points")return `${measures.format(number/100)}%`;
  if(unit==="track_minutes"||unit==="task_minutes")return `${measures.format(number)} min`;
  if(unit==="expected_train_track_seconds")return `${measures.format(number)} expected train·track s`;
  if(unit==="seconds")return `${measures.format(number)} s`;
  return measures.format(number);
}
function change(metric:ComparisonMetric){
  if(metric.favorable_change===null)return "N/A";
  const sign=metric.favorable_change>0?"+":"";
  if(metric.unit==="basis_points")return `${sign}${measures.format(metric.favorable_change/100)} pp favorable`;
  return `${sign}${value(metric.favorable_change,metric.unit)} favorable`;
}
function denominatorDetail(metrics:Record<string,unknown>,key:string){
  const rows=metrics.denominators;
  if(!rows||typeof rows!=="object"||Array.isArray(rows))return "Not applicable";
  const row=(rows as Record<string,unknown>)[key];
  if(!row||typeof row!=="object"||Array.isArray(row))return "Not applicable";
  const record=row as Record<string,unknown>;
  return typeof record.numerator==="number"&&typeof record.denominator==="number"?
    `${measures.format(record.numerator)} / ${measures.format(record.denominator)} ${String(record.unit??"")}`:"Not recorded";
}
function runView(view:WorkspaceView,run:PlanningRun):WorkspaceView{
  return {...view,selected_revision:null,selected_run:{id:run.id,planner_type:run.planner_type,status:run.status,config:{},result:run.result},availability:[],coordination:null};
}
function Side({name,run,revisionId,validation}:{name:string;run:PlanningRun|null;revisionId:string|null;validation?:{status:string;usable:boolean;blockers:string[]}}){
  return <div className="comparison-side"><div><span className="eyebrow">{name}</span><strong>{run?shortId(run.id):"No run recorded"}</strong></div>
    <StatusBadge value={run?.status??"NOT_RUN"}/><div><span>Saved proposal</span><strong>{revisionId?shortId(revisionId):"Not saved"}</strong></div>
    <div><span>Independent validation</span><StatusBadge value={validation?.status??"NOT_RUN"}/></div>
    {validation&&!validation.usable&&<small>{validation.blockers.join(" · ").replaceAll("_"," ")||"Not usable for current review"}</small>}</div>;
}
export default function EvaluationPage(){
  const [comparisonTrack,setComparisonTrack]=useState("ALL");
  const [comparisonScale,setComparisonScale]=useState(1);
  const [comparisonScroll,setComparisonScroll]=useState(0);
  const data=useWorkspaceEvidence();
  const {value:session}=useSession();
  const [baseline,setBaseline]=useState<PlanningRun|null>(null),[optimized,setOptimized]=useState<PlanningRun|null>(null);
  const [comparison,setComparison]=useState<PlanComparison|null>(null);
  const [discovering,setDiscovering]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null);
  const [manualPair,setManualPair]=useState<{snapshotId:string;baseline:string|null;railsync:string|null}|null>(null);
  const [selectedMetric,setSelectedMetric]=useState("reserved_track_minutes");
  const [focus,setFocus]=useState<{side:"baseline"|"railsync";item:Focus}|null>(null);
  const sessionRuns=data.session?.runs??[];
  const baselineSummary=sessionRuns.find(x=>x.planner_type==="BASELINE");
  const optimizedSummary=sessionRuns.find(x=>x.planner_type==="CP_SAT");
  const baselineRunId=baselineSummary?.id??(!data.session&&manualPair?.snapshotId===data.snapshot?.id?manualPair?.baseline:null);
  const optimizedRunId=optimizedSummary?.id??(!data.session&&manualPair?.snapshotId===data.snapshot?.id?manualPair?.railsync:null);
  const cacheKey=data.snapshot&&baselineRunId&&optimizedRunId?`railsync-comparison:${data.snapshot.id}:${baselineRunId}:${optimizedRunId}`:null;
  const baselineRevisionIds=data.runs.find(run=>run.id===baselineRunId)?.revision_ids??[];
  const railsyncRevisionIds=data.runs.find(run=>run.id===optimizedRunId)?.revision_ids??[];
  const snapshotId=data.snapshot?.id??null,snapshotHash=data.snapshot?.content_hash??null;

  useEffect(()=>{const controller=new AbortController();setBaseline(null);setOptimized(null);setError(null);
    if(!baselineRunId||!optimizedRunId)return()=>controller.abort();
    void Promise.all([api<PlanningRun>(`/planning-runs/${baselineRunId}`,{signal:controller.signal}),api<PlanningRun>(`/planning-runs/${optimizedRunId}`,{signal:controller.signal})])
      .then(([left,right])=>{if(!controller.signal.aborted){setBaseline(left);setOptimized(right)}})
      .catch(cause=>{if(!controller.signal.aborted)setError(messageFor(cause))});
    return()=>controller.abort();
  },[baselineRunId,optimizedRunId,data.session?.status]);
  useEffect(()=>{
    const controller=new AbortController();setComparison(null);
    if(!cacheKey||!snapshotId||!snapshotHash||!baselineRevisionIds.length||!railsyncRevisionIds.length){setDiscovering(false);return()=>controller.abort()}
    setDiscovering(true);
    async function discover(){
      async function find(id:string){
        let saved:PlanComparison;
        try{saved=await api<PlanComparison>(`/plan-comparisons/${encodeURIComponent(id)}`,{signal:controller.signal})}
        catch(cause){if(cause instanceof ApiError&&cause.status===404)return false;throw cause}
        if(comparisonMatchesRuns(saved,snapshotId!,snapshotHash!,baselineRevisionIds,railsyncRevisionIds)){
          if(!controller.signal.aborted)setComparison(saved);
          return true;
        }
        return false;
      }
      let cached:string|null=null;
      try{cached=sessionStorage.getItem(cacheKey!)}catch{/* Browser storage is optional. */}
      if(cached&&await find(cached))return;
      // The saved report index restores comparisons in a fresh browser session.
      const seen=new Set(cached?[cached]:[]);
      for(const revisionId of railsyncRevisionIds){
        const index=await api<ReportArtifactIndex>(`/workspace/report-artifacts?plan_revision_id=${encodeURIComponent(revisionId)}`,{signal:controller.signal});
        if(index.revision.snapshot_id!==snapshotId||index.revision.run_id!==optimizedRunId)throw new Error("Saved comparison index does not match the selected run.");
        for(const row of index.comparisons){
          if(row.role!=="RAILSYNC"||seen.has(row.id))continue;
          seen.add(row.id);
          if(await find(row.id))return;
        }
      }
    }
    void discover().catch(cause=>{if(!controller.signal.aborted)setError(messageFor(cause))}).finally(()=>{if(!controller.signal.aborted)setDiscovering(false)});
    return()=>controller.abort();
  // Revision arrays are rebuilt on refresh; IDs are the stable dependency.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[cacheKey,snapshotId,snapshotHash,baselineRunId,optimizedRunId,baselineRevisionIds.join("|"),railsyncRevisionIds.join("|")]);
  const leftRevision=data.runs.find(x=>x.id===baseline?.id)?.revision_ids[0]??null;
  const rightRevision=data.runs.find(x=>x.id===optimized?.id)?.revision_ids[0]??null;
  const eligible=!!baseline?.result_hash&&!!optimized?.result_hash&&baseline.status==="COMPLETED"&&optimized.status==="COMPLETED"&&
    baseline.result?.comparison_eligible===true&&optimized.result?.comparison_eligible===true&&baseline.snapshot_id===optimized.snapshot_id&&baseline.snapshot_id===data.snapshot?.id;
  const canPrepare=["ADMIN","PLANNER","CONTROLLER"].includes(session?.user.role??"");
  async function prepare(){if(!eligible||!baseline||!optimized||!session||!canPrepare||!cacheKey)return;setBusy(true);setError(null);
    try{
      const left=await api<{id:string;plan_hash:string}>("/plan-revisions",{method:"POST",csrf:session.csrf_token,body:{run_id:baseline.id,expected_plan_hash:baseline.result_hash}});
      const right=await api<{id:string;plan_hash:string}>("/plan-revisions",{method:"POST",csrf:session.csrf_token,body:{run_id:optimized.id,expected_plan_hash:optimized.result_hash}});
      await api("/validation-reports",{method:"POST",csrf:session.csrf_token,body:{plan_revision_id:left.id,expected_plan_hash:left.plan_hash}});
      await api("/validation-reports",{method:"POST",csrf:session.csrf_token,body:{plan_revision_id:right.id,expected_plan_hash:right.plan_hash}});
      const saved=await api<PlanComparison>("/plan-comparisons",{method:"POST",csrf:session.csrf_token,body:{baseline_plan_revision_id:left.id,railsync_plan_revision_id:right.id}});
      try{sessionStorage.setItem(cacheKey,saved.id)}catch{/* Comparison remains available in the current view. */}
      setComparison(saved);data.refresh();
    }catch(cause){setError(messageFor(cause))}finally{setBusy(false)}
  }
  const metrics=comparison?.content.metrics;
  const detail=metrics?.[selectedMetric];
  const sameFacts=!!comparison&&!!snapshotId&&!!snapshotHash&&comparisonMatchesRuns(comparison,snapshotId,snapshotHash,baselineRevisionIds,railsyncRevisionIds)&&data.view?.snapshot.id===snapshotId;
  const activeAssignment=focus?.item.kind==="assignment"?(focus.side==="baseline"?baseline:optimized)?.result?.assignments?.find(x=>x.id===focus.item.id):null;
  return <div className="content-flow evaluation-page"><div className="page-heading"><div><span className="eyebrow">SAME-SNAPSHOT EVALUATION</span><h1>Baseline vs RailSync</h1>
    <p>Compare first-feasible planning and CP-SAT coordination using saved intervals, shared facts and declared KPI units.</p></div>
    <div className="page-actions"><button className="button button-outline" onClick={data.refresh}>Refresh evidence</button>
      <button className="button button-primary" disabled={!eligible||busy||!canPrepare} title={!canPrepare?"Planner, controller or administrator role required":undefined} onClick={()=>void prepare()}>{busy?"Preparing…":comparison?"Revalidate comparison":"Prepare comparison"}</button></div></div>
    {(data.error||error)&&<div className="inline-alert" role="alert">{data.error??error}</div>}
    <div className="planning-context panel"><label className="field">Planning snapshot<select value={data.selection.snapshotId??""} onChange={e=>data.selectSnapshot(e.target.value||null)}>
      <option value="">Select a saved snapshot</option>{data.snapshots.map(x=><option key={x.id} value={x.id}>{x.source_scope} · {dateAt(x.horizon_start)} · {x.track_ids.join(", ")} · {shortId(x.id)}</option>)}</select></label>
      <label className="field">Planning session<select value={data.selection.sessionId??""} disabled={!data.snapshot} onChange={e=>data.selectSession(e.target.value||null)}><option value="">Choose saved runs</option>
        {data.sessions.map(x=><option key={x.id} value={x.id}>{dateTimeAt(x.created_at)} · {x.status} · {shortId(x.id)}</option>)}</select></label>
      {data.session?<><div className="context-stamp"><span>Shared input</span><strong>{data.snapshot?shortId(data.snapshot.id):"Not selected"}</strong><small>{data.snapshot?.track_ids.join(", ")??"Select a snapshot"}</small></div>
        <div className="context-stamp"><span>Comparison record</span><strong>{comparison?shortId(comparison.id):discovering?"Checking saved records":"Not prepared"}</strong><small>{comparison?.content.metric_version??"Actual saved intervals required"}</small></div></>:
      <><label className="field">First-feasible run<select value={baselineRunId??""} disabled={!data.snapshot} onChange={e=>setManualPair({snapshotId:data.snapshot!.id,baseline:e.target.value||null,railsync:optimizedRunId??null})}><option value="">Select baseline run</option>
          {data.runs.filter(x=>x.planner_type==="BASELINE").map(x=><option key={x.id} value={x.id}>{x.job_status} · {shortId(x.id)}</option>)}</select></label>
        <label className="field">RailSync CP-SAT run<select value={optimizedRunId??""} disabled={!data.snapshot} onChange={e=>setManualPair({snapshotId:data.snapshot!.id,baseline:baselineRunId??null,railsync:e.target.value||null})}><option value="">Select CP-SAT run</option>
          {data.runs.filter(x=>x.planner_type==="CP_SAT").map(x=><option key={x.id} value={x.id}>{x.job_status} · {shortId(x.id)}</option>)}</select></label></>}</div>
    {!data.snapshot?<div className="panel"><DataState title="Select a planning snapshot" detail="Choose the same saved context used for both planners."/></div>:
    <>
      {!baselineRunId||!optimizedRunId?<div className="panel"><DataState title="Select both saved runs" detail="Choose a completed planning session or a baseline and CP-SAT pair from this snapshot."/></div>:null}
      <div className="comparison-scope panel"><span>Snapshot <strong className="mono">{shortId(data.snapshot.id)}</strong></span><span>{dateTimeAt(data.snapshot.horizon_start)} – {dateTimeAt(data.snapshot.horizon_end)}</span>
        <span>{data.snapshot.source_scope} · {data.snapshot.track_ids.join(", ")}</span><StatusBadge value={data.view?.source_state??"UNKNOWN"}/><span>Comparison {comparison?shortId(comparison.id):"not prepared"}</span></div>
      {data.view?.current_blockers.length?<div className="inline-alert" role="status">Current review blockers: {data.view.current_blockers.join(" · ").replaceAll("_"," ")}. Historical metrics are not current approval evidence.</div>:null}
      <div className="comparison-pair"><Side name="First-feasible baseline" run={baseline} revisionId={comparison?.content.baseline.plan_revision_id??leftRevision} validation={comparison?.current_validation.baseline}/>
        <Side name="RailSync CP-SAT" run={optimized} revisionId={comparison?.content.railsync.plan_revision_id??rightRevision} validation={comparison?.current_validation.railsync}/></div>
      {baselineRunId&&optimizedRunId?(!baseline||!optimized?<div className="panel"><DataState title={error?"Saved run results unavailable":"Loading saved run results"} detail={error?"The API request failed. Review the error above and retry loading the saved results.":"Reading both planner results from the backend…"}/></div>:
        !eligible?<div className="inline-alert">A fair comparison is not available for these runs. Both must have completed, have real incumbents and be marked comparison-eligible on the same snapshot.</div>:null):null}
      {!comparison?(baselineRunId&&optimizedRunId?<div className="panel"><DataState title={discovering?"Finding saved comparisons":"No saved comparison selected"} detail={discovering?"Checking persisted comparisons for this exact snapshot and run pair…":"Prepare comparison to save both proposals, run independent validation and calculate KPIs from their actual intervals. A stale or failed validation remains visible and prevents current claims."}/></div>:null):
        <>
          <div className={comparison.current_claims_permitted&&sameFacts?"inline-success":"inline-alert"} role="status"><strong>{comparison.current_claims_permitted&&sameFacts?"Validated planning comparison":"Historical or unvalidated comparison"}</strong> · {comparison.content.status.replaceAll("_"," ")}. {comparison.current_claims_permitted&&sameFacts?"Both sides currently pass configured prototype validation.":"Values may be inspected, but current benefit claims and approval are blocked."}</div>
          {!sameFacts&&<div className="inline-alert">The saved comparison does not match the selected snapshot, hash or plan revisions. Select its original planning context before interpreting results.</div>}
          {sameFacts&&data.view&&baseline&&optimized&&<><div className="comparison-highlights">{featured.map(key=>{const row=metrics?.[key];return row?<button type="button" key={key} onClick={()=>setSelectedMetric(key)} className={selectedMetric===key?"comparison-highlight selected":"comparison-highlight"}>
            <span>{labels[key]}</span><span className="metric-pair"><span><small>First feasible</small><b>{value(row.baseline,row.unit)}</b></span><span><small>RailSync</small><b>{value(row.railsync,row.unit)}</b></span></span><small className={row.favorable_change!==null&&row.favorable_change<0?"text-urgent":""}>{change(row)}</small></button>:null})}</div>
          <div className="comparison-timelines"><TimeTrackTimeline view={runView(data.view,baseline)} title="Baseline · first feasible" selectedTrack={comparisonTrack} onTrackChange={setComparisonTrack} scale={comparisonScale} onScaleChange={setComparisonScale} scrollOffset={comparisonScroll} onScrollOffsetChange={setComparisonScroll} layers={["train","freight","proposal"]} focus={focus?.side==="baseline"?focus.item:null} onFocus={item=>setFocus({side:"baseline",item})}/>
            <TimeTrackTimeline view={runView(data.view,optimized)} title="RailSync · CP-SAT" selectedTrack={comparisonTrack} onTrackChange={setComparisonTrack} scale={comparisonScale} onScaleChange={setComparisonScale} scrollOffset={comparisonScroll} onScrollOffsetChange={setComparisonScroll} layers={["train","freight","proposal"]} focus={focus?.side==="railsync"?focus.item:null} onFocus={item=>setFocus({side:"railsync",item})}/></div>
          {focus&&<div className="panel panel-body"><strong>{focus.side==="baseline"?"Baseline":"RailSync"} · {focus.item.kind.replaceAll("_"," ")}</strong>
            {activeAssignment?<p>{activeAssignment.track_ids.join(", ")} · {dateTimeAt(activeAssignment.possession_start)} – {timeAt(activeAssignment.possession_end)} IST · {activeAssignment.request_ids.length} request(s) · {activeAssignment.mode.replaceAll("_"," ")}</p>:<p>Source interval {shortId(focus.item.id)}. The same confirmed traffic and forecast layers appear in both timelines.</p>}</div>}
          <section className="panel"><div className="panel-header"><div><h2>Metric evidence</h2><p>Positive favorable change means a better value for the metric’s stated direction; negative values remain visible.</p></div></div>
            <div className="comparison-table-scroll"><table className="comparison-table"><thead><tr><th>Metric</th><th>First feasible</th><th>RailSync</th><th>Favorable change</th><th>Improvement</th></tr></thead><tbody>
              {Object.entries(metrics??{}).map(([key,row])=><tr key={key} className={selectedMetric===key?"selected-row":undefined}><th scope="row"><button type="button" onClick={()=>setSelectedMetric(key)}>{labels[key]??key.replaceAll("_"," ")}</button></th>
                <td>{value(row.baseline,row.unit)}</td><td>{value(row.railsync,row.unit)}</td><td className={row.favorable_change===null?"":row.favorable_change<0?"text-urgent":""}>{change(row)}</td>
                <td>{row.improvement_percent===null?"N/A":`${row.improvement_percent>0?"+":""}${measures.format(row.improvement_percent)}%`}</td></tr>)}</tbody></table></div></section>
          {detail&&<section className="panel panel-body comparison-method"><div><span className="eyebrow">METRIC DEFINITION</span><h2>{labels[selectedMetric]??selectedMetric.replaceAll("_"," ")}</h2><p>{detail.formula}</p><small>Unit: {detail.unit.replaceAll("_"," ")} · Direction: {detail.direction.replaceAll("_"," ")} · Percentage: {detail.status==="BASELINE_ZERO_PERCENT_NA"?"N/A because baseline is zero":detail.status.replaceAll("_"," ")}</small></div>
            <div><strong>Declared numerator / denominator</strong><p>Baseline: {denominatorDetail(comparison.content.baseline.metrics,selectedMetric)}</p><p>RailSync: {denominatorDetail(comparison.content.railsync.metrics,selectedMetric)}</p></div></section>}
          </>}
          <p className="planning-disclaimer">Planned tasks are not completed work. Forecast exposure is not measured delay. Planned track availability is not asset reliability. CP-SAT optimality applies only to generated candidates. Operational authorization remains external.</p>
        </>}
    </>}
  </div>;
}
