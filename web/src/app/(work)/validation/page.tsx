"use client";

import Link from "next/link";
import {useState} from "react";
import {api,dateAt,dateTimeAt,messageFor,shortId,timeAt} from "@/lib/api";
import {useSession} from "@/lib/session";
import {useWorkspaceEvidence} from "@/lib/use-workspace";
import {DataState} from "@/components/data-state";
import {StatusBadge} from "@/components/status-badge";
import {TimeTrackTimeline} from "@/components/time-track-timeline";
import type {Focus} from "@/lib/timeline";
import type {ValidationFinding,ValidationReport,WorkspaceView} from "@/lib/types";

const severity=(finding:ValidationFinding)=>finding.status==="ERROR"?0:1;
function label(value:string){return value.replaceAll("_"," ")}
function ref(value:unknown){return typeof value==="string"?value:null}
function FindingSources({view,finding}:{view:WorkspaceView;finding:ValidationFinding}){
  const e=finding.evidence;
  const plan=view.selected_revision?.content;
  const assignmentIds=[ref(e.candidate_id),ref(e.left),ref(e.right)].filter((x):x is string=>!!x);
  const assignments=plan?.assignments?.filter(x=>assignmentIds.includes(x.id))??[];
  const train=view.facts.occupancy.find(x=>x.id===ref(e.occupancy_id));
  const freight=view.facts.freight.find(x=>x.id===ref(e.forecast_id));
  const coa=view.facts.coa.find(x=>x.id===ref(e.coa_id));
  const restriction=view.facts.network.find(x=>x.id===ref(e.restriction_id));
  const demand=view.demands.find(x=>x.request_id===ref(e.request_id));
  const resource=view.facts.resources?.find(x=>x.id===ref(e.resource_id));
  const resourceDuties=plan?.assignments?.flatMap(x=>x.allocations.filter(a=>a.resource_id===ref(e.resource_id)))??[];
  return <div className="finding-sources">
    {assignments.map(assignment=><div key={assignment.id}><strong>Proposed possession · {shortId(assignment.id)}</strong><span>{assignment.track_ids.join(", ")} · {dateTimeAt(assignment.possession_start)} – {timeAt(assignment.possession_end)} IST</span><small>{assignment.request_ids.length} included request(s)</small></div>)}
    {train&&<div><strong>Confirmed train · {train.train_id}</strong><span>{train.track_id} · {dateTimeAt(train.enter_at)} – {timeAt(train.exit_at)} IST</span><small>Occupancy record {shortId(train.id)}</small></div>}
    {freight&&<div><strong>Forecast · {freight.external_id}</strong><span>{freight.track_id} · {dateTimeAt(freight.start_at)} – {timeAt(freight.end_at)} IST</span><small>Expected count {freight.expected_count}; forecast is not measured delay</small></div>}
    {coa&&<div><strong>COA declaration · {coa.external_id}</strong><span>{coa.track_id} · {dateTimeAt(coa.start_at)} – {timeAt(coa.end_at)} IST</span></div>}
    {restriction&&<div><strong>Restriction · {restriction.id}</strong><span>{String(restriction.payload.type??restriction.kind)} · {String(restriction.payload.start??"time not recorded")} – {String(restriction.payload.end??"time not recorded")}</span></div>}
    {demand&&<div><strong>Maintenance request · {shortId(demand.request_id)}</strong><span>{demand.request.department} · {demand.request.issue_type} · {demand.request.footprint.join(", ")}</span><small>Power {demand.access_requirements.power_block} · Isolation {demand.access_requirements.electrical_isolation_zone??"not declared"}</small></div>}
    {resource&&<div><strong>Resource · {String(resource.id)}</strong><span>{String(resource.resource_type??"Type not recorded")} · {String(resource.department??"Department not recorded")}</span></div>}
    {resourceDuties.map((duty,index)=><div key={`${duty.resource_id}:${index}`}><strong>Assigned duty · {duty.resource_id}</strong><span>{duty.track_id} · {dateTimeAt(duty.start_at)} – {timeAt(duty.end_at)} IST</span><small>Request {shortId(duty.request_id)}</small></div>)}
    {!assignments.length&&!train&&!freight&&!coa&&!restriction&&!demand&&!resource&&!resourceDuties.length&&<p className="muted">The report identifies no source interval for this finding. The exact recorded fields appear below; no conflict interval is inferred.</p>}
  </div>;
}
function downloadReport(report:ValidationReport){
  const link=document.createElement("a"),url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:"application/json"}));
  link.href=url;link.download=`r-maps-validation-${report.id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export default function ValidationPage(){
  const data=useWorkspaceEvidence();
  const {value:session}=useSession();
  const [category,setCategory]=useState("ALL"),[findingIndex,setFindingIndex]=useState<number|null>(null);
  const [focus,setFocus]=useState<Focus|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[message,setMessage]=useState<string|null>(null);
  const selectedRevision=data.selection.revisionId;
  const view=data.view?.selected_revision?.id===selectedRevision?data.view:null;
  const report=view?.validation??null;
  const checks=report?.result.checks??[];
  const findings=checks.flatMap(c=>c.findings).sort((a,b)=>severity(a)-severity(b)||a.category.localeCompare(b.category)||a.code.localeCompare(b.code));
  const visible=category==="ALL"?findings:findings.filter(x=>x.category===category);
  const selected=visible[findingIndex??0]??visible[0];
  const evidenceFocus:Focus|null=selected?.evidence.occupancy_id?{kind:"train",id:String(selected.evidence.occupancy_id)}:
    selected?.evidence.forecast_id?{kind:"freight",id:String(selected.evidence.forecast_id)}:
    selected?.evidence.candidate_id?{kind:"assignment",id:String(selected.evidence.candidate_id)}:null;
  const revisionOptions=data.runs.flatMap(run=>run.revision_ids.map(id=>({id,run})));
  async function revalidate(){if(!view?.selected_revision||!session)return;setBusy(true);setError(null);setMessage(null);
    try{const next=await api<ValidationReport>("/validation-reports",{method:"POST",csrf:session.csrf_token,
      body:{plan_revision_id:view.selected_revision.id,expected_plan_hash:view.selected_revision.plan_hash}});
      setMessage(`Independent validation recorded ${next.status} at ${dateTimeAt(next.checked_at)}. Current review use: ${next.usable_for_review?"usable":"blocked"}.`);
      setCategory("ALL");setFindingIndex(null);setFocus(null);data.refresh();
    }catch(cause){setError(messageFor(cause))}finally{setBusy(false)}
  }
  return <div className="content-flow validation-page"><div className="page-heading"><div><span className="eyebrow">INDEPENDENT FEASIBILITY GATE</span><h1>Validation Center</h1>
    <p>Inspect configured constraint checks and the exact saved evidence behind a proposed block plan.</p></div>
    <div className="page-actions"><button className="button button-outline" onClick={data.refresh}>Refresh evidence</button>
      <button className="button button-primary" disabled={!view?.selected_revision||busy||!["PLANNER","ADMIN","CONTROLLER"].includes(session?.user.role??"")} onClick={()=>void revalidate()}>{busy?"Validating…":"Run independent validation"}</button></div></div>
    {(data.error||error)&&<div className="inline-alert" role="alert">{data.error??error}</div>}{message&&<div className="inline-success" role="status">{message}</div>}
    <div className="planning-context panel"><label className="field">Planning snapshot<select value={data.selection.snapshotId??""} onChange={e=>{data.selectSnapshot(e.target.value||null);setCategory("ALL");setFindingIndex(null);setFocus(null)}}>
      <option value="">Select a saved snapshot</option>{data.snapshots.map(x=><option key={x.id} value={x.id}>{x.source_scope} · {dateAt(x.horizon_start)} · {shortId(x.id)}</option>)}</select></label>
      <label className="field">Saved proposal revision<select value={selectedRevision??""} disabled={!data.snapshot} onChange={e=>{data.selection.selectRevision(e.target.value||null);setCategory("ALL");setFindingIndex(null);setFocus(null)}}>
        <option value="">Select a proposal</option>{revisionOptions.map(({id,run})=><option key={id} value={id}>{run.planner_type} · {shortId(id)} · {run.job_status}</option>)}</select></label>
      <div className="context-stamp"><span>Snapshot</span><strong>{data.snapshot?shortId(data.snapshot.id):"Not selected"}</strong><small>{data.snapshot?.source_scope??"Choose a planning state"}</small></div>
      <div className="context-stamp"><span>Report</span><strong>{report?shortId(report.id):"Not validated"}</strong><small>{report?.result.validator_version??"Independent result required"}</small></div></div>
    {!data.snapshot?<div className="panel"><DataState title="Select a planning snapshot" detail="Validation results are bound to a saved railway planning state and proposal revision."/></div>:
    !selectedRevision?<div className="panel"><DataState title="Select a saved proposal" detail="Choose the exact plan revision. A completed solver run alone is not a validated proposal."/></div>:
    !view?<div className="panel"><DataState title={data.viewLoading?"Loading validation evidence":"Proposal evidence unavailable"} detail={data.viewLoading?"Reading the selected proposal and latest report…":"Refresh the workspace or inspect the API error above."}/></div>:
    <>
      <div className="validation-summary panel"><div><span>Recorded result</span><StatusBadge value={report?.status??"NOT_VALIDATED"}/></div>
        <div><span>Current review use</span><StatusBadge value={report?.usable_for_review?"USABLE":"BLOCKED"}/></div>
        <div><span>Checked</span><strong>{report?dateTimeAt(report.checked_at):"Never"}</strong></div>
        <div><span>Proposal revision</span><strong className="mono">{shortId(view.selected_revision?.id)}</strong></div>
        <div><span>Plan hash</span><strong className="mono">{shortId(view.selected_revision?.plan_hash)}</strong></div></div>
      <div className="inline-note">A PASS means compliance with configured prototype constraints at the recorded check time. It is not railway safety certification or operational authorization.</div>
      {view.current_blockers.length>0&&<div className="inline-alert" role="status"><strong>Current blockers:</strong> {view.current_blockers.join(" · ").replaceAll("_"," ")}</div>}
      {!report?<div className="panel"><DataState title="Not validated" detail="No independent validation report exists for this revision. Run validation to obtain a recorded PASS, FAIL or ERROR; approval remains blocked."/></div>:
      <>
        <div className="validation-overview panel"><span>{checks.length} configured categories</span><strong>{findings.length} finding(s)</strong><span>{report.result.checks_performed??"Unknown"} checks performed</span><span>Validator {report.result.validator_version??"version unavailable"}</span>
          <button className="button button-outline" onClick={()=>downloadReport(report)}>Export report JSON</button></div>
        <div className="validation-layout"><section className="panel validation-categories"><div className="panel-header"><div><h2>Constraint categories</h2><p>Filtering does not change the recorded result</p></div></div>
          <div className="validation-category-list"><button className={category==="ALL"?"selected":""} onClick={()=>{setCategory("ALL");setFindingIndex(null);setFocus(null)}}><strong>All findings</strong><span>{findings.length}</span></button>
            {checks.map(check=><button key={check.category} className={category===check.category?"selected":""} onClick={()=>{setCategory(check.category);setFindingIndex(null);setFocus(null)}}>
              <strong>{label(check.category)}</strong><StatusBadge value={check.status}/><span>{check.findings.length}</span></button>)}</div></section>
          <section className="panel validation-findings"><div className="panel-header"><div><h2>Recorded findings</h2><p>{category==="ALL"?"All categories":label(category)} · {visible.length} shown of {findings.length}</p></div></div>
            {visible.length?<div className="validation-finding-list">{visible.map((finding,index)=><button key={`${finding.category}:${finding.code}:${index}`} className={selected===finding?"selected":""} onClick={()=>{setFindingIndex(index);setFocus(null)}}>
              <StatusBadge value={finding.status}/><div><strong>{label(finding.code)}</strong><small>{label(finding.category)}</small></div><span>{Object.entries(finding.evidence).filter(([,v])=>typeof v==="string").slice(0,2).map(([k,v])=>`${label(k)} ${shortId(String(v))}`).join(" · ")||"Evidence fields below"}</span></button>)}</div>:
              <DataState title={category==="ALL"?"No findings recorded":"No findings in this category"} detail={category==="ALL"?"Read the recorded result and current blockers above. An empty finding list alone does not grant review use.":"Choose another category to inspect its recorded checks."}/>}</section>
          <aside className="panel validation-inspector"><div className="panel-header"><div><h2>Finding evidence</h2><p>Only source and interval facts linked by the report</p></div></div>
            {selected?<div className="panel-body validation-evidence"><div><StatusBadge value={selected.status}/><h3>{label(selected.code)}</h3><span className="muted">{label(selected.category)}</span></div>
              <FindingSources view={view} finding={selected}/><div className="evidence-subhead">Recorded fields</div>
              {Object.keys(selected.evidence).length?<dl>{Object.entries(selected.evidence).map(([key,value])=><div key={key}><dt>{label(key)}</dt><dd>{typeof value==="string"?value:JSON.stringify(value)}</dd></div>)}</dl>:
                <p className="muted">This finding has no additional fields in the saved report.</p>}
              <div className="validation-source-links"><Link href="/planning">Open Planning Workspace</Link><Link href="/corridor">Open Corridor evidence</Link></div></div>:
              <DataState title="Select a finding" detail="Choose a failed or error check to inspect its saved evidence. A current blocker may also be listed above without an interval."/>}</aside></div>
        <TimeTrackTimeline view={view} title="Proposal and operating context" layers={["train","freight","coa","restriction","commitment","proposal"]} focus={focus??evidenceFocus} onFocus={setFocus}/>
      </>}
    </>}
    <p className="planning-disclaimer">Independent validation reports preserve historical findings. Current review use comes from the backend’s freshness and hash checks; a past PASS can be blocked today.</p>
  </div>;
}
