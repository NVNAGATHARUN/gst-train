"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {api,ApiError,dateAt,dateTimeAt,messageFor,shortId,timeAt} from "@/lib/api";
import {useSession} from "@/lib/session";
import {useWorkspaceEvidence} from "@/lib/use-workspace";
import {DataState} from "@/components/data-state";
import {DepartmentBadge,StatusBadge} from "@/components/status-badge";
import type {PlanningSchedule,ScheduleAssignment} from "@/lib/types";

type ScheduleType="WEEKLY"|"MONTHLY";
const human=(value:string)=>value.replaceAll("_"," ").toLowerCase();
function dateKey(value:string,timezone:string){
  const parts=new Intl.DateTimeFormat("en-GB",{timeZone:timezone,year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date(value));
  const part=(type:string)=>parts.find(x=>x.type===type)?.value??"";
  return `${part("year")}-${part("month")}-${part("day")}`;
}
function calendarDates(start:string,count:number){
  const [year,month,day]=start.split("-").map(Number);
  return Array.from({length:count},(_,index)=>new Date(Date.UTC(year,month-1,day+index)).toISOString().slice(0,10));
}
function assignmentsOnDay(schedule:PlanningSchedule,day:string){
  return schedule.content.assignments.filter(block=>{
    const first=dateKey(block.possession_start,schedule.timezone);
    const last=dateKey(new Date(new Date(block.possession_end).getTime()-1).toISOString(),schedule.timezone);
    return first<=day&&day<=last;
  });
}
function Block({block,selected,onSelect}:{block:ScheduleAssignment;selected:boolean;onSelect:()=>void}){
  return <button type="button" className={`schedule-block ${selected?"selected":""}`} onClick={onSelect}>
    <span className="schedule-block-top"><strong>{block.request_ids.length>1?"Integrated":"Single work"} · {shortId(block.id)}</strong><StatusBadge value={block.commitment_status}/></span>
    <span>{block.track_ids.join(", ")} · {dateTimeAt(block.possession_start)} – {dateTimeAt(block.possession_end)}</span>
    <small>{block.tasks.map(x=>x.department==="ENGINEERING"?"ENG":x.department==="SNT"?"S&T":"TRD").join(" + ")} · {block.tasks.length} task(s) · freight coverage {human(block.forecast_coverage_status)}</small>
  </button>;
}
export default function SchedulesPage(){
  const data=useWorkspaceEvidence();
  const {value:session}=useSession();
  const [kind,setKind]=useState<ScheduleType>("WEEKLY");
  const [weekStart,setWeekStart]=useState("");
  const [month,setMonth]=useState("");
  const [scheduleId,setScheduleId]=useState<string|null>(null);
  const [openId,setOpenId]=useState("");
  const [schedule,setSchedule]=useState<PlanningSchedule|null>(null);
  const [busy,setBusy]=useState(false),[loadingSaved,setLoadingSaved]=useState(false),[exporting,setExporting]=useState<"json"|"csv"|null>(null);
  const [error,setError]=useState<string|null>(null),[notice,setNotice]=useState<string|null>(null);
  const [selectedDay,setSelectedDay]=useState<string|null>(null),[selectedBlock,setSelectedBlock]=useState<string|null>(null);
  const revisionOptions=useMemo(()=>data.runs.flatMap(run=>run.revision_ids.map(id=>({id,run}))),[data.runs]);
  const revisionId=data.selection.revisionId??data.view?.selected_revision?.id??revisionOptions.find(x=>x.run.planner_type==="CP_SAT")?.id??revisionOptions[0]?.id??null;
  const currentSnapshot=data.snapshot;
  const scheduleMatches=!!schedule&&!!currentSnapshot&&schedule.content.plan_revision.snapshot_hash===currentSnapshot.content_hash;
  const revisionMatches=!!schedule&&revisionId===schedule.plan_revision_id;
  const associatedSnapshot=schedule?data.snapshots.find(x=>x.content_hash===schedule.content.plan_revision.snapshot_hash):null;
  useEffect(()=>{setScheduleId(new URLSearchParams(window.location.search).get("schedule_id"))},[]);
  useEffect(()=>{if(!currentSnapshot)return;
    const start=dateKey(currentSnapshot.horizon_start,"Asia/Kolkata");
    setWeekStart(start);setMonth(start.slice(0,7));
  },[currentSnapshot]);
  useEffect(()=>{if(!scheduleId){setSchedule(null);return}const controller=new AbortController();setLoadingSaved(true);setError(null);
    void api<PlanningSchedule>(`/planning-schedules/${encodeURIComponent(scheduleId)}`,{signal:controller.signal})
      .then(saved=>{if(!controller.signal.aborted){setSchedule(saved);setOpenId(saved.id);setSelectedDay(saved.content.period.local_start);setSelectedBlock(null)}})
      .catch(cause=>{if(!controller.signal.aborted){setSchedule(null);setError(messageFor(cause))}})
      .finally(()=>{if(!controller.signal.aborted)setLoadingSaved(false)});
    return()=>controller.abort();
  },[scheduleId]);
  function showSaved(id:string){setScheduleId(id);const url=new URL(window.location.href);url.searchParams.set("schedule_id",id);window.history.replaceState(null,"",url.pathname+url.search)}
  async function generate(){if(!revisionId||!session)return;setBusy(true);setError(null);setNotice(null);
    try{
      const body=kind==="WEEKLY"?{plan_revision_id:revisionId,schedule_type:kind,timezone_name:"Asia/Kolkata",week_start:weekStart}:
        {plan_revision_id:revisionId,schedule_type:kind,timezone_name:"Asia/Kolkata",year:Number(month.slice(0,4)),month:Number(month.slice(5,7))};
      const saved=await api<PlanningSchedule>("/planning-schedules",{method:"POST",csrf:session.csrf_token,body});
      setSchedule(saved);setScheduleId(saved.id);setOpenId(saved.id);setSelectedDay(saved.content.period.local_start);setSelectedBlock(null);
      const url=new URL(window.location.href);url.searchParams.set("schedule_id",saved.id);window.history.replaceState(null,"",url.pathname+url.search);
      setNotice(saved.duplicate?"An identical saved artifact was returned.":"Immutable schedule artifact saved. Status and validation reflect generation time.");
    }catch(cause){setError(messageFor(cause))}finally{setBusy(false)}
  }
  async function download(format:"json"|"csv"){
    if(!schedule)return;setExporting(format);setError(null);
    try{
      const response=await fetch(`/api/v1/planning-schedules/${encodeURIComponent(schedule.id)}/export?format=${format}`,{credentials:"same-origin",cache:"no-store"});
      if(!response.ok){let detail:unknown=`HTTP ${response.status}`;try{detail=(await response.json()).detail??detail}catch{}throw new ApiError(response.status,detail)}
      if(response.headers.get("X-RMAPS-Content-Hash")!==schedule.content_hash)throw new Error("Export hash does not match the displayed schedule. Refresh the artifact before exporting.");
      const url=URL.createObjectURL(await response.blob());
      const anchor=document.createElement("a");anchor.href=url;anchor.download=`rmaps-${schedule.schedule_type.toLowerCase()}-${schedule.id}.${format}`;
      document.body.appendChild(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(cause){setError(cause instanceof Error&&!(cause instanceof ApiError)?cause.message:messageFor(cause))}finally{setExporting(null)}
  }
  const dates=schedule?calendarDates(schedule.content.period.local_start,schedule.content.period.calendar_days):[];
  const day=selectedDay&&dates.includes(selectedDay)?selectedDay:dates[0];
  const dayBlocks=schedule&&day?assignmentsOnDay(schedule,day):[];
  const block=schedule?.content.assignments.find(x=>x.id===selectedBlock)??dayBlocks[0]??null;
  const roleCanCreate=["ADMIN","PLANNER","CONTROLLER"].includes(session?.user.role??"");
  return <div className="content-flow schedules-page">
    <div className="page-heading"><div><span className="eyebrow">IMMUTABLE CALENDAR ARTIFACT</span><h1>Weekly &amp; Monthly Block Plan</h1>
      <p>Read the exact saved proposal across local calendar days. Planned work remains separate from actual execution and railway authorization.</p></div>
      <div className="page-actions"><button className="button button-outline" onClick={data.refresh}>Refresh evidence</button></div></div>
    {(data.error||error)&&<div className="inline-alert" role="alert">{error??data.error}</div>}{notice&&<div className="inline-success" role="status">{notice}</div>}
    <section className="panel"><div className="panel-header"><div><h2>Build from a saved proposal</h2><p>Full seven-day or calendar-month snapshot coverage is required</p></div></div>
      <div className="schedule-controls">
        <label className="field">Planning snapshot<select value={currentSnapshot?.id??""} onChange={e=>data.selectSnapshot(e.target.value||null)}><option value="">Select snapshot</option>{data.snapshots.map(x=><option key={x.id} value={x.id}>{shortId(x.id)} · {dateAt(x.horizon_start)} – {dateAt(x.horizon_end)} · {x.source_scope}</option>)}</select></label>
        <label className="field">Saved plan revision<select value={revisionId??""} onChange={e=>data.selection.selectRevision(e.target.value||null)}><option value="">Select revision</option>{revisionOptions.map(x=><option key={x.id} value={x.id}>{shortId(x.id)} · {x.run.planner_type} · {x.run.job_status}</option>)}</select></label>
        <label className="field">Period<select value={kind} onChange={e=>setKind(e.target.value as ScheduleType)}><option value="WEEKLY">Seven days</option><option value="MONTHLY">Calendar month</option></select></label>
        {kind==="WEEKLY"?<label className="field">First local day<input type="date" value={weekStart} onChange={e=>setWeekStart(e.target.value)}/></label>:
          <label className="field">Local month<input type="month" value={month} onChange={e=>setMonth(e.target.value)}/></label>}
        <button className="button button-primary" disabled={!revisionId||!roleCanCreate||busy||(kind==="WEEKLY"?!weekStart:!month)} onClick={()=>void generate()}>{busy?"Saving…":"Create schedule"}</button>
      </div>
      <div className="schedule-source-note">{currentSnapshot?<><strong>{currentSnapshot.source_scope}</strong> snapshot · horizon {dateTimeAt(currentSnapshot.horizon_start)} – {dateTimeAt(currentSnapshot.horizon_end)} · {currentSnapshot.track_ids.join(", ")}</>:"Select a planning snapshot."} {currentSnapshot?.scenario_id&&"Isolated scenario; no operational reservation."}</div>
      {!roleCanCreate&&<p className="quiet-note schedule-role-note">This role can read and export saved schedules but cannot create them.</p>}
    </section>
    <div className="schedule-open"><label className="field">Open saved artifact by ID<input value={openId} onChange={e=>setOpenId(e.target.value.trim())} placeholder="Paste an existing schedule ID"/></label><button className="button button-outline" disabled={!openId||loadingSaved} onClick={()=>showSaved(openId)}>Open</button>{scheduleId&&<span className="quiet-note">Artifact link: /schedules?schedule_id={scheduleId}</span>}</div>
    {loadingSaved&&<DataState title="Opening saved schedule" detail="Reading the immutable calendar artifact from the backend."/>}
    {!loadingSaved&&!schedule&&<DataState title="No schedule selected" detail="Choose a saved plan revision and calendar period, or open an existing schedule ID. A short snapshot cannot produce a complete weekly or monthly artifact."/>}
    {!loadingSaved&&schedule&&<>
      <section className="panel"><div className="panel-header"><div><h2>{schedule.schedule_type==="WEEKLY"?"Seven-day":"Monthly"} plan · {schedule.content.period.local_start} to {schedule.content.period.local_end_exclusive} (exclusive)</h2><p>Saved {dateTimeAt(schedule.created_at)} · Asia/Kolkata · {schedule.content.period.calendar_days} calendar days</p></div><StatusBadge value={schedule.content.status}/></div>
        <div className="schedule-status-strip"><div><span>Block proposals</span><strong>{schedule.content.counts.assignments}</strong></div><div><span>Maintenance tasks planned</span><strong>{schedule.content.counts.tasks}</strong></div><div><span>Firm / tentative / attention</span><strong>{schedule.content.counts.firm} / {schedule.content.counts.tentative} / {schedule.content.counts.requires_attention}</strong></div><div><span>Deferred requests</span><strong>{schedule.content.counts.deferred}</strong></div><div><span>Validation at generation</span><StatusBadge value={schedule.content.validation.status}/></div></div>
        <div className="schedule-context-line"><span>Revision <strong>{shortId(schedule.plan_revision_id)}</strong> · snapshot hash <strong>{shortId(schedule.content.plan_revision.snapshot_hash)}</strong></span><span>Controller: <strong>{schedule.content.controller_decision?.action??"No decision"}</strong></span><span>Authority: <strong>software proposal only</strong></span></div>
        {(!scheduleMatches||!revisionMatches)&&<div className="inline-note">{!currentSnapshot?"No planning snapshot is selected for current-evidence comparison.":!scheduleMatches?"The selected snapshot differs from this saved artifact.":"The selected plan revision differs from this saved artifact."} The artifact remains historical. {associatedSnapshot&&!scheduleMatches&&<button className="schedule-source-link" onClick={()=>data.selectSnapshot(associatedSnapshot.id)}>Select matching snapshot</button>}</div>}
        {!schedule.content.validation.currently_usable&&<div className="inline-alert">Validation was not currently usable when this schedule was generated. {schedule.content.validation.blockers.map(human).join(" · ")||"Review the saved report."}</div>}
        <div className="schedule-export"><span>Content hash: <code>{shortId(schedule.content_hash)}</code> · Generated at {dateTimeAt(schedule.content.generated_at)}</span><button className="button button-outline" disabled={!!exporting} onClick={()=>void download("json")}>{exporting==="json"?"Exporting…":"Export JSON"}</button><button className="button button-outline" disabled={!!exporting} onClick={()=>void download("csv")}>{exporting==="csv"?"Exporting…":"Export CSV"}</button></div>
      </section>
      <div className="schedule-layout"><section className="panel schedule-calendar"><div className="panel-header"><div><h2>Calendar overview</h2><p>Select a day to inspect exact possession and task intervals</p></div></div>{schedule.schedule_type==="MONTHLY"&&<div className="schedule-weekdays">{["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map(x=><span key={x}>{x}</span>)}</div>}<div className={`schedule-day-grid ${schedule.schedule_type==="WEEKLY"?"schedule-week":""}`}>
        {schedule.schedule_type==="MONTHLY"&&Array.from({length:(new Date(`${schedule.content.period.local_start}T00:00:00Z`).getUTCDay()+6)%7},(_,i)=><span className="schedule-empty-cell" key={`blank-${i}`}/>)}
        {dates.map(date=>{const blocks=assignmentsOnDay(schedule,date);return <button key={date} className={`schedule-day ${day===date?"selected":""}`} onClick={()=>{setSelectedDay(date);setSelectedBlock(null)}}><span>{dateAt(`${date}T12:00:00+05:30`)}</span><strong>{blocks.length?`${blocks.length} block${blocks.length===1?"":"s"}`:"No block"}</strong>{blocks.slice(0,3).map(x=><small key={x.id} className={`schedule-day-item status-${x.commitment_status.toLowerCase()}`}>{timeAt(x.possession_start)} · {x.track_ids.join(", ")}</small>)}{blocks.length>3&&<small>+{blocks.length-3} more</small>}</button>})}
      </div></section><aside className="panel schedule-day-detail"><div className="panel-header"><div><h2>{day?dateAt(`${day}T12:00:00+05:30`):"Selected day"}</h2><p>{dayBlocks.length} saved block proposal(s) intersect this day</p></div></div><div className="schedule-day-list">{dayBlocks.length?dayBlocks.map(x=><Block key={x.id} block={x} selected={block?.id===x.id} onSelect={()=>setSelectedBlock(x.id)}/>):<DataState title="No planned block" detail="This saved plan has no assignment intersecting the selected day."/>}</div></aside></div>
      {block&&<section className="panel"><div className="panel-header"><div><h2>Block detail · {shortId(block.id)}</h2><p>{dateTimeAt(block.possession_start)} – {dateTimeAt(block.possession_end)} · {block.track_ids.join(", ")}</p></div><StatusBadge value={block.commitment_status}/></div><div className="schedule-detail-grid"><div><h3>Maintenance and handback</h3>{block.tasks.map(task=><div className="schedule-task" key={task.request_id}><DepartmentBadge department={task.department}/><strong>{task.issue_type} · {shortId(task.request_id)}</strong><span>Setup {dateTimeAt(task.setup_start)} – {dateTimeAt(task.setup_end)}</span><span>Work {dateTimeAt(task.work_start)} – {dateTimeAt(task.work_end)}</span><span>Restoration {dateTimeAt(task.restore_start)} – {dateTimeAt(task.restore_end)}</span></div>)}</div><div><h3>Named resources and evidence</h3>{block.allocations.length?block.allocations.map((a,i)=><div className="schedule-resource" key={`${a.resource_id}:${i}`}><strong>{a.resource_id} · {a.resource_type}</strong><span>{dateTimeAt(a.start_at)} – {dateTimeAt(a.end_at)}</span></div>):<p className="muted">No allocation recorded.</p>}<div className="schedule-evidence"><span>Freight coverage: <strong>{human(block.forecast_coverage_status)}</strong></span><span>Reservation scope: <strong>{block.reservation_scope??"none"}</strong></span><span>Data valid until: <strong>{schedule.content.uncertainty.data_valid_until?dateTimeAt(schedule.content.uncertainty.data_valid_until):"not declared"}</strong></span></div></div></div></section>}
      <div className="schedule-lower"><section className="panel"><div className="panel-header"><div><h2>Deferred maintenance</h2><p>Recorded in the same saved plan revision</p></div></div><div className="schedule-deferred">{schedule.content.deferred.length?schedule.content.deferred.map(x=><div key={x.request_id}><strong>{shortId(x.request_id)}</strong><span>{human(x.reason)}</span></div>):<DataState title="None recorded" detail="No deferred request is recorded in this plan artifact."/>}</div></section><section className="panel"><div className="panel-header"><div><h2>Coverage and authority</h2><p>Limits carried by the immutable schedule</p></div></div><div className="schedule-coverage"><strong>Freight declaration by track</strong>{Object.entries(schedule.content.uncertainty.freight_coverage_declared_until_by_track).map(([track,until])=><div key={track}><span>{track}</span><span>{until?dateTimeAt(until):"Not declared"}</span></div>)}<p>FIRM means a matching software reservation and usable validation at artifact generation. It is not a granted railway block. This historical artifact is not live approval evidence.</p><Link href="/review">Open controller review →</Link></div></section></div>
    </>}
  </div>;
}
