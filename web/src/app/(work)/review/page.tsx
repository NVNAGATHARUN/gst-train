"use client";

import Link from "next/link";
import {useRouter} from "next/navigation";
import {useEffect,useState} from "react";
import {api,ApiError,dateAt,dateTimeAt,messageFor,shortId,timeAt} from "@/lib/api";
import {useSession} from "@/lib/session";
import {useWorkspaceEvidence} from "@/lib/use-workspace";
import {DataState} from "@/components/data-state";
import {StatusBadge} from "@/components/status-badge";
import {TimeTrackTimeline} from "@/components/time-track-timeline";
import {TaskStages} from "@/components/task-stages";
import type {Focus} from "@/lib/timeline";
import type {Candidate,WorkspaceView} from "@/lib/types";

type Action="APPROVE"|"REJECT"|"REPLAN";
type Decision={id:string;idempotency_key:string;plan_revision_id:string;validation_report_id:string|null;action:Action;scope:string;expected_operational_revision:number;resulting_operational_revision:number;reason:string;result:Record<string,unknown>;created_at:string;authority:string;reservations?:Array<Record<string,unknown>>};
type Revision={id:string;lineage_id:string;revision:number;run_id:string;snapshot_id:string;parent_id:string|null;plan_hash:string;snapshot_hash:string;edit:Record<string,unknown>;content:{assignments?:Candidate[];selected_candidate_ids?:string[];deferred?:Array<{request_id:string;reason:string}>};created_at:string;authority:string;current_state:{status:string;disruption_event_ids:string[];execution_blocker?:string};decisions:Decision[]};
type Freeze={scope:string;operational_revision:number;checked_at:string;status:string;policy:null|{id:string;revision:number;freeze_minutes:number};commitments:Array<{candidate_id:string;plan_revision_id:string;decision_id:string;frozen:boolean;reasons:string[];blockers:string[]}>};
type Difference={plan_revision_id:string;content_hash:string;payload:Record<string,unknown>};
type ReviewContext={revision:Revision;freeze:Freeze;priorApproval:Decision|null;difference:Difference|null};
type Pending={action:Action;revisionId:string;key:string;path:string;body:Record<string,unknown>};
const label=(value:string)=>value.replaceAll("_"," ");
const reviewError=(cause:unknown)=>cause instanceof Error&&!(cause instanceof ApiError)?cause.message:messageFor(cause);
function Detail({title,children}:{title:string;children:React.ReactNode}){return <div className="review-detail"><span>{title}</span><strong>{children}</strong></div>}
function AssignmentCard({candidate,view}:{candidate:Candidate;view:WorkspaceView}){
  const demands=candidate.request_ids.map(id=>view.demands.find(x=>x.request_id===id)).filter(x=>!!x);
  return <article className="review-block"><div className="review-block-head"><div><strong>{candidate.request_ids.length>1?"Integrated block":"Proposed block"} · {shortId(candidate.id)}</strong><span>{candidate.track_ids.join(", ")} · {dateTimeAt(candidate.possession_start)} – {timeAt(candidate.possession_end)} IST</span></div><span>{candidate.request_ids.length} request(s)</span></div>
    <TaskStages candidate={candidate}/>
    <div className="review-access">{demands.map(d=><div key={d.request_id}><span>{shortId(d.request_id)}</span><span>Line {d.access_requirements.line_block}</span><span>Power {d.access_requirements.power_block}</span><span>S&amp;T {d.access_requirements.snt_disconnection}</span><span>Isolation {d.access_requirements.electrical_isolation_zone??"not declared"}</span><span>Provision {d.access_requirements.provision_status}</span></div>)}</div>
    <div className="review-resources"><strong>Named resources</strong>{candidate.allocations.length?candidate.allocations.map((a,i)=><span key={`${a.resource_id}:${i}`}>{a.resource_id} · {a.resource_type} · {timeAt(a.start_at)}–{timeAt(a.end_at)}</span>):<span>No allocation recorded</span>}</div></article>;
}
export default function ReviewPage(){
  const router=useRouter();
  const data=useWorkspaceEvidence();const {value:session}=useSession();
  const [context,setContext]=useState<ReviewContext|null>(null),[contextError,setContextError]=useState<string|null>(null),[contextLoading,setContextLoading]=useState(false),[contextVersion,setContextVersion]=useState(0);
  const [reason,setReason]=useState(""),[action,setAction]=useState<Action>("APPROVE"),[busy,setBusy]=useState(false),[pending,setPending]=useState<Pending|null>(null);
  const [error,setError]=useState<string|null>(null),[notice,setNotice]=useState<string|null>(null),[conflict,setConflict]=useState(false),[decision,setDecision]=useState<Decision|null>(null);
  const [editing,setEditing]=useState(false),[candidateQuery,setCandidateQuery]=useState(""),[selectedIds,setSelectedIds]=useState<string[]>([]);
  const [focus,setFocus]=useState<Focus|null>(null);
  const [scenarioSource,setScenarioSource]=useState<string|null>(null);
  const revisionId=data.selection.revisionId;
  const view=data.view?.selected_revision?.id===revisionId?data.view:null;
  const validContext=!!view&&!!context&&context.revision.id===revisionId&&context.revision.snapshot_id===data.snapshot?.id&&context.revision.plan_hash===view.selected_revision?.plan_hash;
  const report=view?.validation??null;
  const scenario=!!data.snapshot?.scenario_id;
  const controller=session?.user.role==="CONTROLLER";
  const candidates=view?.coordination?.result.candidates??[];
  const assignments=view?.selected_revision?.content.assignments??[];
  const currentIds=view?.selected_revision?.content.selected_candidate_ids??assignments.map(x=>x.id);
  const initialSelection=currentIds.join("\u0000");
  const refreshEvidence=data.refresh;
  const changes=selectedIds.length!==currentIds.length||selectedIds.some(x=>!currentIds.includes(x));
  const alreadyApproved=context?.revision.decisions.some(x=>x.action==="APPROVE")??false;
  const packetUsable=validContext&&!scenario&&view.source_state==="CURRENT"&&view.current_blockers.length===0&&report?.status==="PASS"&&report.usable_for_review&&report.plan_hash===context.revision.plan_hash&&context.revision.current_state.status==="NO_EVENT_INVALIDATION"&&context.freeze.status==="ASSESSED";
  const canSubmit=controller&&validContext&&!scenario&&!busy&&!pending&&!conflict&&reason.trim().length>=3&&
    (action!=="APPROVE"||packetUsable&&!alreadyApproved)&&(action!=="REJECT"||!alreadyApproved&&!context.priorApproval);
  const revisionOptions=data.runs.flatMap(run=>run.revision_ids.map(id=>({id,run})));

  useEffect(()=>{setContext(null);setContextError(null);setPending(null);setConflict(false);setDecision(null);setEditing(false);setReason("");setError(null);setNotice(null)},[revisionId]);
  useEffect(()=>{const id=data.snapshot?.scenario_id;if(!id){setScenarioSource(null);return}let live=true;setScenarioSource(null);
    void api<{source_snapshot_id:string}>(`/what-if-scenarios/${id}`).then(x=>{if(live)setScenarioSource(x.source_snapshot_id)}).catch(()=>{if(live)setScenarioSource(null)});
    return()=>{live=false};
  },[data.snapshot?.scenario_id]);
  useEffect(()=>{if(!revisionId)return;let live=true;setContextLoading(true);setContextError(null);
    async function read(){
      const [revision,freeze]=await Promise.all([api<Revision>(`/plan-revisions/${revisionId}`),api<Freeze>(`/plan-revisions/${revisionId}/freeze-context`)]);
      let difference:Difference|null=null;
      try{difference=await api<Difference>(`/plan-revisions/${revisionId}/differences`)}catch(cause){if(!(cause instanceof ApiError&&cause.status===404))throw cause}
      let parent=revision.parent_id,priorApproval:Decision|null=null,depth=0;
      while(parent){if(++depth>50)throw new Error("Revision ancestry exceeds review limit");const ancestor=await api<Revision>(`/plan-revisions/${parent}`);
        if(ancestor.lineage_id!==revision.lineage_id)throw new Error("Revision lineage mismatch");
        const approved=ancestor.decisions.filter(x=>x.action==="APPROVE").at(-1);if(approved&&!priorApproval)priorApproval=approved;
        parent=ancestor.parent_id;
      }
      if(live)setContext({revision,freeze,priorApproval,difference});
    }
    void read().catch(cause=>{if(live){setContext(null);setContextError(reviewError(cause))}}).finally(()=>{if(live)setContextLoading(false)});
    return()=>{live=false};
  },[revisionId,contextVersion]);
  useEffect(()=>{if(!revisionId)return;const timer=setInterval(()=>{refreshEvidence();setContextVersion(x=>x+1)},15000);return()=>clearInterval(timer)},[revisionId,refreshEvidence]);
  useEffect(()=>{setSelectedIds(initialSelection?initialSelection.split("\u0000"):[])},[revisionId,initialSelection]);
  function refresh(){data.refresh();setContextVersion(x=>x+1)}
  async function checkPacket(expected:ReviewContext,forAction:Action){
    const [latest,freeze,workspace]=await Promise.all([api<Revision>(`/plan-revisions/${expected.revision.id}`),api<Freeze>(`/plan-revisions/${expected.revision.id}/freeze-context`),
      api<WorkspaceView>(`/snapshots/${expected.revision.snapshot_id}/workspace?plan_revision_id=${expected.revision.id}`)]);
    if(latest.plan_hash!==expected.revision.plan_hash||freeze.operational_revision!==expected.freeze.operational_revision||latest.current_state.status!==expected.revision.current_state.status){throw new Error("The proposal or scope revision changed during review. Refresh and review it again.")}
    if(forAction==="APPROVE"&&(!workspace.validation?.usable_for_review||workspace.validation.id!==report?.id||workspace.current_blockers.length||workspace.source_state!=="CURRENT")){
      throw new Error("The validation or source state changed during review. Refresh before approval.")
    }
  }
  async function postPending(item:Pending){setBusy(true);setError(null);setNotice(null);
    try{const saved=await api<Decision>(item.path,{method:"POST",csrf:session?.csrf_token,body:item.body,signal:AbortSignal.timeout(20000)});
      setDecision(saved);setPending(null);setReason("");setNotice(`${saved.action} recorded as decision ${shortId(saved.id)} in ${saved.scope} scope. Railway authorization remains external.`);refresh();
    }catch(cause){if(cause instanceof ApiError&&[401,403,409,422].includes(cause.status)){setPending(null);if(cause.status===409){setConflict(true);refresh()}}
      else setNotice("Decision result unconfirmed. Check the saved record or retry the exact request with the same key; do not start another decision.");
      setError(reviewError(cause));
    }finally{setBusy(false)}
  }
  async function submit(){if(!canSubmit||!context||!session)return;setBusy(true);setError(null);setNotice(null);
    try{await checkPacket(context,action);
      const key=crypto.randomUUID(),body:Record<string,unknown>={idempotency_key:key,expected_plan_hash:context.revision.plan_hash,expected_operational_revision:context.freeze.operational_revision,reason:reason.trim()};
      let path=`/plan-revisions/${context.revision.id}/decisions`;
      if(action==="REPLAN")path=`/plan-revisions/${context.revision.id}/replan`;
      else{body.action=action;body.validation_report_id=action==="APPROVE"?report!.id:null;body.supersedes_decision_id=action==="APPROVE"?context.priorApproval?.id??null:null}
      const item={action,revisionId:context.revision.id,key,path,body};setPending(item);setBusy(false);await postPending(item);
    }catch(cause){setBusy(false);setConflict(true);setError(reviewError(cause));refresh()}
  }
  async function resolvePending(){if(!pending)return;setBusy(true);setError(null);
    try{const latest=await api<Revision>(`/plan-revisions/${pending.revisionId}`),saved=latest.decisions.find(x=>x.idempotency_key===pending.key);
      if(saved){setDecision(saved);setPending(null);setReason("");setNotice(`${saved.action} was already recorded as decision ${shortId(saved.id)}. No duplicate request was sent.`);refresh()}
      else setNotice("No matching decision is recorded yet. Retry the exact request below; it retains the original idempotency key.");
    }catch(cause){setError(messageFor(cause))}finally{setBusy(false)}
  }
  async function modify(){if(!controller||!validContext||!context||!session||scenario||!changes||reason.trim().length<3||busy||pending)return;
    setBusy(true);setError(null);setNotice(null);
    try{const child=await api<Revision>(`/plan-revisions/${context.revision.id}/modifications`,{method:"POST",csrf:session.csrf_token,
      body:{expected_revision:context.revision.revision,expected_plan_hash:context.revision.plan_hash,selected_candidate_ids:selectedIds,reason:reason.trim()}});
      data.selection.selectRevision(child.id);setEditing(false);setReason("");setNotice(`Child proposal ${shortId(child.id)} saved. Independent validation is required before approval.`);refresh();
    }catch(cause){setError(messageFor(cause));if(cause instanceof ApiError&&cause.status===409){setConflict(true);refresh()}}finally{setBusy(false)}
  }
  return <div className="content-flow review-page"><div className="page-heading"><div><span className="eyebrow">HUMAN DECISION BOUNDARY</span><h1>Controller Review</h1><p>Review an exact software proposal, its current evidence and the decision that would be recorded.</p></div>
    <div className="page-actions"><button className="button button-outline" onClick={()=>{setContext(null);setConflict(false);refresh()}} disabled={busy}>Refresh review context</button><Link className="button button-outline" href="/validation">Open Validation Center</Link>{validContext&&<a className="button button-primary" href="#controller-decision">Review decision</a>}</div></div>
    {(data.error||contextError||error)&&<div className="inline-alert" role="alert">{data.error??contextError??error}</div>}{notice&&<div className={pending?"inline-alert":"inline-success"} role="status">{notice}</div>}
    <div className="planning-context panel"><label className="field">Planning snapshot<select value={data.selection.snapshotId??""} onChange={e=>data.selectSnapshot(e.target.value||null)}><option value="">Select a snapshot</option>
      {data.snapshots.map(x=><option key={x.id} value={x.id}>{x.source_scope} · {dateAt(x.horizon_start)} · {shortId(x.id)}</option>)}</select></label>
      <label className="field">Proposal revision<select value={revisionId??""} disabled={!data.snapshot} onChange={e=>data.selection.selectRevision(e.target.value||null)}><option value="">Select a saved proposal</option>
        {revisionOptions.map(({id,run})=><option key={id} value={id}>{run.planner_type} · {shortId(id)} · {run.job_status}</option>)}</select></label>
      <div className="context-stamp"><span>Source scope</span><strong>{data.snapshot?.source_scope??"Not selected"}</strong><small>{scenario?"Isolated what-if scenario":"Saved railway planning state"}</small></div>
      <div className="context-stamp"><span>Signed-in role</span><strong>{session?.user.role??"Unknown"}</strong><small>{controller?"Controller decisions available":"Read-only review"}</small></div></div>
    {!data.snapshot?<div className="panel"><DataState title="Select a planning snapshot" detail="Controller review is bound to one saved snapshot and one exact proposal revision."/></div>:
    !revisionId?<div className="panel"><DataState title="Select a saved proposal" detail="Solver output must be materialized as a plan revision before a controller can review it."/></div>:
    !validContext?<div className="panel"><DataState title={data.viewLoading||contextLoading?"Loading decision packet":"Decision packet unavailable"} detail={data.viewLoading||contextLoading?"Reading the proposal, validator, freeze context and decision history…":"Refresh evidence. Hash, scope or API mismatches block decisions."}/></div>:
    <>
      <div className="review-decision-strip panel"><div><span>Exact revision</span><strong>{shortId(context.revision.id)} · r{context.revision.revision}</strong></div><div><span>Scope</span><StatusBadge value={context.freeze.scope}/></div>
        <div><span>Validation</span><StatusBadge value={report?.status??"NOT_VALIDATED"}/></div><div><span>Current review use</span><StatusBadge value={packetUsable?"USABLE":"BLOCKED"}/></div>
        <div><span>State revision</span><strong>{context.freeze.operational_revision}</strong></div><div><span>Authority</span><strong>Software proposal only</strong></div></div>
      {scenario&&<div className="inline-alert"><strong>Scenario results cannot be approved.</strong> This scenario writes no source reservations. {scenarioSource?
        <button className="review-source-link" onClick={()=>{data.selectSnapshot(scenarioSource);router.push("/planning")}}>Open source planning snapshot {shortId(scenarioSource)} →</button>:
        <span>The source snapshot link is unavailable; inspect the scenario record before using its results.</span>}</div>}
      {!controller&&<div className="inline-note">Your role can inspect this packet. Approve, modify, reject and replan writes require a CONTROLLER session.</div>}
      {alreadyApproved&&<div className="inline-note">This exact revision already has a recorded approval. Changes require a child proposal and controlled supersession; its existing reservations remain in force until the backend commits a replacement.</div>}
      {!alreadyApproved&&context.priorApproval&&<div className="inline-note">A prior revision in this lineage was approved. Use a validated replacement proposal for controlled supersession; rejection cannot silently release its reservations.</div>}
      {conflict&&<div className="inline-alert"><strong>Packet changed during review.</strong> Your reason is preserved. Inspect the refreshed hashes, validation and state revision before selecting another action.</div>}
      {view.current_blockers.length>0&&<div className="inline-alert"><strong>Current blockers:</strong> {view.current_blockers.map(label).join(" · ")}</div>}
      <div className="review-packet"><section className="panel"><div className="panel-header"><div><h2>Proposal packet</h2><p>Saved intervals and affected work, not an operating order</p></div></div>
        <div className="review-meta"><Detail title="Snapshot / plan hash">{shortId(context.revision.snapshot_hash)} / {shortId(context.revision.plan_hash)}</Detail>
          <Detail title="Created">{dateTimeAt(context.revision.created_at)}</Detail><Detail title="Source validity">{label(context.revision.current_state.status)}</Detail>
          <Detail title="Requests / blocks">{view.demands.length} / {assignments.length}</Detail><Detail title="Previous revision">{context.revision.parent_id?shortId(context.revision.parent_id):"First revision"}</Detail>
          <Detail title="Recorded report">{report?`${shortId(report.id)} · ${dateTimeAt(report.checked_at)}`:"No independent report"}</Detail></div>
        <div className="review-blocks">{assignments.length?assignments.map(x=><AssignmentCard key={x.id} candidate={x} view={view}/>):<DataState title="No blocks in proposal" detail="Inspect the solver and deferred work; no possession is inferred."/>}</div>
        {!!view.selected_revision?.content.deferred?.length&&<div className="review-deferred"><strong>Deferred work</strong>{view.selected_revision.content.deferred.map(x=><span key={x.request_id}>{shortId(x.request_id)} · {label(x.reason)}</span>)}</div>}</section>
        <aside className="review-side"><section className="panel"><div className="panel-header"><div><h2>Validation and current state</h2><p>Approval requires a current usable PASS</p></div></div><div className="review-side-body">
          <Detail title="Recorded result"><StatusBadge value={report?.status??"NOT_VALIDATED"}/></Detail><Detail title="Current usability"><StatusBadge value={report?.usable_for_review?"USABLE":"BLOCKED"}/></Detail>
          <Detail title="Report blockers">{report?.current_blockers.length?report.current_blockers.map(label).join(" · "):"None reported"}</Detail>
          <Detail title="Freeze status">{label(context.freeze.status)}</Detail><Detail title="Freeze policy">{context.freeze.policy?`r${context.freeze.policy.revision} · ${context.freeze.policy.freeze_minutes} min`:"Not configured"}</Detail>
          <Detail title="Frozen commitments">{context.freeze.commitments.filter(x=>x.frozen).length} of {context.freeze.commitments.length}</Detail>
          {context.freeze.commitments.map(x=><div className="review-commitment" key={`${x.decision_id}:${x.candidate_id}`}><strong>{shortId(x.candidate_id)} · {x.frozen?"Frozen":"Active"}</strong><span>{x.reasons.map(label).join(" · ")||"No freeze reason recorded"}</span>{x.blockers.length>0&&<small>{x.blockers.map(label).join(" · ")}</small>}</div>)}
          <Link href="/validation">Inspect all constraint findings →</Link></div></section>
          <section className="panel"><div className="panel-header"><div><h2>Why this work?</h2><p>Saved request-level explanation evidence</p></div></div><div className="review-side-body">
            {view.explanations.length?view.explanations.map((x,i)=><div className="review-explanation" key={String(x.request_id??i)}><strong>{shortId(String(x.request_id))} · {String(x.outcome)}</strong>
              <span>{x.priority&&typeof x.priority==="object"?`Rule priority: ${String((x.priority as Record<string,unknown>).priority_band??"recorded")}`:"Priority not recorded"}</span>
              <span>{x.selected_candidate_id?`Selected ${shortId(String(x.selected_candidate_id))}`:x.deferred_reason?`Deferred: ${label(String(x.deferred_reason))}`:"No candidate reason recorded"}</span></div>):
              <DataState title="Explanations not generated" detail="No request-level explanation artifact is saved for this revision."/>}
            {controller&&view.explanations.length===0&&<button className="button button-outline" disabled={busy} onClick={()=>void (async()=>{setBusy(true);setError(null);try{await api(`/plan-revisions/${context.revision.id}/explanations`,{method:"POST",csrf:session!.csrf_token,body:{}});refresh()}catch(cause){setError(messageFor(cause))}finally{setBusy(false)}})()}>Generate saved explanations</button>}
          </div></section></aside></div>
      <TimeTrackTimeline view={view} title="Traffic and proposed blocks" layers={["train","freight","coa","restriction","commitment","proposal"]} focus={focus} onFocus={setFocus}/>
      <div className="review-lower"><section className="panel"><div className="panel-header"><div><h2>Revision and decision history</h2><p>Only persisted decisions count</p></div></div><div className="review-side-body">
        {context.difference?<div className="review-difference"><strong>Replacement difference · {shortId(context.difference.content_hash)}</strong><pre>{JSON.stringify(context.difference.payload,null,2)}</pre></div>:
          <p className="muted">No replacement-difference artifact is recorded for this revision.</p>}
        {context.priorApproval&&<div className="inline-note">Prior lineage approval {shortId(context.priorApproval.id)} will be supplied as the controlled supersede reference. Its reservations remain until the backend transaction succeeds.</div>}
        {context.revision.decisions.length?context.revision.decisions.map(x=><div className="review-history" key={x.id}><StatusBadge value={x.action}/><strong>{shortId(x.id)}</strong><span>{dateTimeAt(x.created_at)} · {x.scope} · state r{x.expected_operational_revision}→r{x.resulting_operational_revision}</span><small>{x.reason}</small></div>):<p className="muted">No controller decision recorded for this revision.</p>}
        {decision&&<div className="inline-success">Last confirmed: {decision.action} · {decision.id} · resulting state r{decision.resulting_operational_revision}.</div>}
      </div></section>
      <section className="panel controller-decision" id="controller-decision"><div className="panel-header"><div><h2>Controller action</h2><p>Reason and exact evidence are bound to the submitted record</p></div></div><div className="review-side-body">
        {pending?<div className="review-pending"><strong>Decision result unconfirmed</strong><span>{pending.action} · key {shortId(pending.key)}</span><p>Use the same request key. Do not submit a different decision until this result is resolved.</p>
          <div className="review-actions"><button className="button button-outline" disabled={busy} onClick={()=>void resolvePending()}>Check saved decision</button><button className="button button-primary" disabled={busy} onClick={()=>void postPending(pending)}>Retry exact request</button></div></div>:
        <><div className="review-action-tabs">{(["APPROVE","MODIFY","REJECT","REPLAN"] as const).map(x=><button key={x} className={(x==="MODIFY"?editing:!editing&&action===x)?"selected":""}
          disabled={!controller||scenario||busy} onClick={()=>{setEditing(x==="MODIFY");if(x!=="MODIFY")setAction(x);setError(null)}}>{x==="APPROVE"?"Approve proposal":x==="MODIFY"?"Modify proposal":x==="REJECT"?"Reject proposal":"Replan"}</button>)}</div>
          <label className="field">
            <span style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Controller reason</span>
              <button type="button" style={{ background: "none", border: "none", color: "var(--accent, #0284c7)", cursor: "pointer", fontSize: "11px", padding: 0 }}
                onClick={() => setReason("Reviewed the saved proposal evidence; decision recorded for the planning workflow only.")}>
                Fill neutral reason
              </button>
            </span>
            <textarea value={reason} maxLength={1000} onChange={e=>setReason(e.target.value)} placeholder="Record the operational planning reason (minimum 3 characters)" disabled={!controller||scenario}/>
          </label>
          {editing?<><p className="quiet-note">Choose only generated candidates. Saving creates a child revision; it does not inherit validation. The backend checks frozen work and the independent validator must run again.</p>
            <label className="field">Filter generated candidates<input value={candidateQuery} onChange={e=>setCandidateQuery(e.target.value)} placeholder="Candidate, request or track ID"/></label>
            <div className="review-candidates">{candidates.filter(x=>`${x.id} ${x.request_ids.join(" ")} ${x.track_ids.join(" ")}`.toLowerCase().includes(candidateQuery.toLowerCase())).map(x=><label key={x.id}><input type="checkbox" checked={selectedIds.includes(x.id)} onChange={e=>setSelectedIds(previous=>e.target.checked?[...previous,x.id]:previous.filter(id=>id!==x.id))}/><span><strong>{shortId(x.id)} · {x.mode}</strong><small>{x.track_ids.join(", ")} · {dateTimeAt(x.possession_start)} – {timeAt(x.possession_end)} · {x.request_ids.length} request(s)</small></span></label>)}</div>
            <button className="button button-primary" disabled={!controller||scenario||!changes||reason.trim().length<3||busy||conflict||view.source_state!=="CURRENT"} onClick={()=>void modify()}>Save child proposal</button></>:
          <><div className="review-submit-note">{action==="APPROVE"?"Approval reserves the saved blocks in this proposal's scope. It never grants railway operating authority.":action==="REJECT"?"Rejection records the reason and scope revision; it does not approve or execute work.":"Replan queues a new same-snapshot run only if current source facts still match."}</div>
            <button className="button button-primary" disabled={!canSubmit} onClick={()=>void submit()}>{action==="APPROVE"?"Record proposal approval":action==="REJECT"?"Record rejection":"Request replan"}</button>
            {!canSubmit && (
              <div style={{ fontSize: "12px", color: "var(--amber, #b45309)", marginTop: "8px", display: "flex", flexDirection: "column", gap: "4px" }}>
                {reason.trim().length < 3 && <span>⚠️ <strong>Reason required:</strong> Type at least 3 characters in the Controller reason box above.</span>}
                {scenario && <span>⚠️ <strong>Isolated simulation:</strong> What-If scenarios are simulations and cannot be recorded as operational decisions. Switch to the primary corridor snapshot.</span>}
                {action === "APPROVE" && (!report || report.status !== "PASS") && <span>⚠️ <strong>Validation required:</strong> Independent safety validation must run and PASS before approval (current: {report?.status ?? "NOT RUN"}). Open Validation in sidebar.</span>}
                {action === "APPROVE" && alreadyApproved && <span>ℹ️ <strong>Already approved:</strong> This plan revision has already been confirmed and approved.</span>}
              </div>
            )}
          </>}
          {!controller&&<p className="muted">Sign in with a provisioned CONTROLLER role to submit a decision.</p>}</>}
      </div></section></div>
      <p className="planning-disclaimer">Approval here is a controller decision on an R-MAPS software proposal. External railway authorization, possession grant, isolation and actual execution remain separate.</p>
    </>}
  </div>;
}
