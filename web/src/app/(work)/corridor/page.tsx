"use client";

import {useMemo,useState} from "react";
import {TimeTrackTimeline} from "@/components/time-track-timeline";
import {DataState} from "@/components/data-state";
import {StatusBadge} from "@/components/status-badge";
import {dateAt,dateTimeAt,shortId,timeAt} from "@/lib/api";
import {timelineItems} from "@/lib/timeline";
import type {Focus,Layer,TimelineItem} from "@/lib/timeline";
import {useWorkspaceEvidence} from "@/lib/use-workspace";
import type {Window} from "@/lib/types";

const corridorLayers:Layer[]=["train","freight","coa","restriction","commitment","released","capacity"];
function text(value:unknown){return typeof value==="string"||typeof value==="number"?String(value):"Not declared"}
function minuteAt(base:string,minute:unknown){return typeof minute==="number"?dateTimeAt(new Date(Date.parse(base)+minute*60_000).toISOString()):"Unavailable"}
function gapMinutes(interval:TimelineItem,window:Window){
  const a=Date.parse(interval.start),b=Date.parse(interval.end),c=Date.parse(window.start_at),d=Date.parse(window.end_at);
  return Math.round(Math.min(Math.abs(b-c),Math.abs(a-d),a<=c&&b>=c?0:Infinity,a<=d&&b>=d?0:Infinity)/60_000);
}
export default function CorridorPage(){
  const data=useWorkspaceEvidence();
  const [calculationId,setCalculationId]=useState<string|null>(null);
  const [focus,setFocus]=useState<Focus|null>(null);
  const [selectedTrack,setSelectedTrack]=useState("ALL");
  const view=data.view;
  const calculation=view?.availability.find(x=>x.id===calculationId)??view?.availability[0];
  const windows=calculation?.result.windows??[];
  const track=selectedTrack==="ALL"||view?.snapshot.track_ids.includes(selectedTrack)?selectedTrack:"ALL";
  const visibleWindows=windows.filter(x=>track==="ALL"||x.track_ids.includes(track));
  const selectedWindow=focus?.kind==="window"?visibleWindows.find(x=>x.id===focus.id):undefined;
  const window=selectedWindow??visibleWindows[0];
  const timelineView=useMemo(()=>view?{...view,availability:calculation?[calculation]:[]}:null,[view,calculation]);
  const focusedSource=view&&focus&&focus.kind!=="window"?timelineItems(view).find(item=>item.kind===focus.kind&&item.id===focus.id):null;
  const nearby=view&&window?timelineItems(view).filter(x=>
    ["train","freight","coa","restriction","commitment","released"].includes(x.layer)&&window.track_ids.includes(x.track))
    .sort((a,b)=>gapMinutes(a,window)-gapMinutes(b,window)).slice(0,12):[];
  const coveringCoa=window&&view?view.facts.coa.filter(x=>window.track_ids.includes(x.track_id)&&
    Date.parse(x.start_at)<Date.parse(window.end_at)&&Date.parse(x.end_at)>Date.parse(window.start_at)):[];
  return <div className="content-flow corridor-page"><div className="page-heading"><div><span className="eyebrow">CAPACITY EVIDENCE</span><h1>Corridor &amp; COA availability</h1>
    <p>Understand how recorded operating facts constrain each backend-calculated maintenance window.</p></div>
    <div className="page-actions"><button className="button button-outline" onClick={data.refresh}>Refresh evidence</button></div></div>
    {data.error&&<div className="inline-alert" role="alert">{data.error}</div>}
    <div className="planning-context panel"><label className="field">Planning snapshot<select value={data.selection.snapshotId??""} onChange={e=>{data.selectSnapshot(e.target.value||null);setFocus(null);setCalculationId(null)}}>
      <option value="">Select a saved snapshot</option>{data.snapshots.map(x=><option key={x.id} value={x.id}>{x.source_scope} · {dateAt(x.horizon_start)} · {x.track_ids.join(", ")} · {shortId(x.id)}</option>)}</select></label>
      <label className="field">Saved planning run<select value={data.runId??""} disabled={!data.snapshot||!!data.selection.revisionId} onChange={e=>{data.selectRun(e.target.value||null);setFocus(null);setCalculationId(null)}}><option value="">Snapshot facts only</option>
        {data.runs.map(x=><option key={x.id} value={x.id}>{x.planner_type} · {x.job_status} · {shortId(x.id)}</option>)}</select></label>
      <label className="field">Availability calculation<select value={calculation?.id??""} disabled={!view?.availability.length} onChange={e=>{setCalculationId(e.target.value);setFocus(null)}}><option value="">No calculation</option>
        {view?.availability.map(x=><option key={x.id} value={x.id}>{(x.policy.track_ids as string[]).join(", ")} · {shortId(x.id)}</option>)}</select></label>
      <div className="context-stamp"><span>Source state</span><strong>{view?.source_state??"NOT SELECTED"}</strong><small>{data.snapshot?.source_scope??"Choose a snapshot"}</small></div></div>
    {data.selection.revisionId&&<div className="inline-note">Showing availability bound to selected proposal <span className="mono">{shortId(data.selection.revisionId)}</span>. To inspect another run, select it in Planning Workspace first.</div>}
    {view?.current_blockers.length?<div className="inline-alert" role="status">Current source/review blockers: {view.current_blockers.join(" · ").replaceAll("_"," ")}. Historical calculation remains visible but is not current approval evidence.</div>:null}
    {data.loading||data.viewLoading&&!view?<div className="panel"><DataState title="Loading corridor evidence" detail="Reading saved facts and calculation results…"/></div>:
    !data.snapshot?<div className="panel"><DataState title="Select a snapshot" detail="Choose a saved railway planning state to see occupancy, COA and restrictions."/></div>:
    !view?<div className="panel"><DataState title="Workspace unavailable" detail="Refresh the selected snapshot or inspect the API error above."/></div>:
    <><div className="corridor-summary"><div><span>Selected track scope</span><strong>{calculation?text((calculation.policy.track_ids as string[]).join(", ")):view.snapshot.track_ids.join(", ")}</strong></div>
      <div><span>Calculated windows</span><strong>{calculation?windows.length:"Not computed"}</strong></div>
      <div><span>COA records</span><strong>{view.facts.coa.length}</strong></div><div><span>Confirmed occupancy</span><strong>{view.facts.occupancy.length}</strong></div>
      <div><span>Freight envelopes</span><strong>{view.facts.freight.length}</strong></div><div><span>Commitments / recorded possession</span><strong>{view.facts.commitments?.length??0} / {view.facts.released_possessions?.length??0}</strong></div></div>
      {calculation&&<div className="capacity-derivation" aria-label="Saved capacity derivation"><div><span>01 · ACCESS ENVELOPE</span><strong>COA declarations</strong><small>{view.facts.coa.length} saved records across snapshot tracks</small></div><span aria-hidden="true">→</span><div><span>02 · PROTECTION</span><strong>Traffic &amp; restrictions</strong><small>{text(calculation.policy.clearance_before_minutes)} / {text(calculation.policy.clearance_after_minutes)} min train clearance · {calculation.policy.protect_freight_envelope===true?"freight protected":calculation.policy.protect_freight_envelope===false?"freight not subtracted":"freight policy unknown"}</small></div><span aria-hidden="true">→</span><div><span>03 · SAVED OUTPUT</span><strong>{visibleWindows.length} derived windows</strong><small>{track==="ALL"?"All tracks in this calculation":track} · not a possession authorization</small></div></div>}
      <div className="corridor-layout"><div className="corridor-main">
        {timelineView&&<TimeTrackTimeline view={timelineView} focus={focus} onFocus={setFocus} title="Traffic, declarations & derived capacity" layers={corridorLayers}
          selectedTrack={track} onTrackChange={setSelectedTrack}/>}
        {!calculation?<div className="panel"><DataState title="No saved availability calculation in this context" detail="Select a planning run with a prepared corridor calculation. Source occupancy and COA remain visible above; free capacity has not been computed for this selection."/></div>:
          <section className="panel"><div className="panel-header"><div><h2>Derived capacity windows</h2><p>Actual output from calculation <span className="mono">{shortId(calculation.id)}</span></p></div></div>
            {visibleWindows.length===0?<DataState title="No usable windows on the selected track" detail="The calculation returned no matching interval. Inspect exclusions and source conflicts below."/>:
              <div className="capacity-list">{visibleWindows.map(x=><button className={`capacity-row ${window?.id===x.id?"capacity-row-active":""}`} key={x.id}
                onClick={()=>setFocus({kind:"window",id:x.id})}><span className="mono">{shortId(x.id)}</span><strong>{timeAt(x.start_at)}–{timeAt(x.end_at)} IST</strong><span>{x.track_ids.join(", ")}</span><b>{x.usable_minutes} min</b></button>)}</div>}
          </section>}
        {calculation&&<section className="panel"><div className="panel-header"><div><h2>Excluded intervals & source conflicts</h2><p>Recorded backend reasons, including minimum duration and COA conflicts</p></div></div>
          {calculation.result.excluded.length===0&&calculation.result.source_conflicts.length===0?<div className="panel-body muted">No exclusions or source conflicts were recorded by this calculation.</div>:
          <div className="exclusion-list">{calculation.result.excluded.map((x,index)=><div key={`ex:${index}`}><StatusBadge value="EXCLUDED"/><strong>{text(x.code).replaceAll("_"," ")}</strong><span>{text(x.track_id??(Array.isArray(x.track_ids)?x.track_ids.join(", "):undefined))}</span>
            <small>{minuteAt(view.snapshot.horizon_start,x.start_minute)} – {minuteAt(view.snapshot.horizon_start,x.end_minute)}</small></div>)}
            {calculation.result.source_conflicts.map((x,index)=><div key={`conflict:${index}`}><StatusBadge value="CONFLICT"/><strong>{text(x.code).replaceAll("_"," ")}</strong><span>{text(x.track_id)}</span><small>Source evidence {shortId(text(x.evidence_id))}</small></div>)}
          </div>}</section>}
      </div><aside className="corridor-inspector panel"><div className="panel-header"><div><h2>Why this window exists</h2><p>Policy and nearby saved source facts</p></div></div>
        {focusedSource&&<section className="corridor-source-selection" aria-label="Selected source interval"><span className="eyebrow">SELECTED {focusedSource.layer.toUpperCase()}</span><h3>{focusedSource.label}</h3><dl><div><dt>Track</dt><dd>{focusedSource.track}</dd></div><div><dt>From</dt><dd>{dateTimeAt(focusedSource.start)}</dd></div><div><dt>To</dt><dd>{dateTimeAt(focusedSource.end)}</dd></div></dl><button type="button" className="button button-text compact-button" onClick={()=>setFocus(window?{kind:"window",id:window.id}:null)}>Return to window evidence</button></section>}
        {!calculation?<DataState title="Calculation required" detail="Select a saved run to see the actual corridor policy and derived windows."/>:<div className="panel-body corridor-evidence">
          <div className="corridor-rule"><strong>Recorded derivation</strong><p>COA allowance is narrowed by confirmed train occupancy and configured clearance{calculation.policy.protect_freight_envelope===true?", protected freight envelopes":""}, restrictions and recorded possession history. The backend intersects the resulting free intervals across the requested tracks.</p></div>
          <div className="detail-list"><div><span>Train clearance before / after</span><strong>{text(calculation.policy.clearance_before_minutes)} / {text(calculation.policy.clearance_after_minutes)} min</strong></div>
            <div><span>Minimum useful duration</span><strong>{text(calculation.policy.minimum_useful_minutes)} min</strong></div>
            <div><span>Freight protection</span><strong>{calculation.policy.protect_freight_envelope===true?"Protected":calculation.policy.protect_freight_envelope===false?"Not subtracted by this policy":"Not declared"}</strong></div>
            <div><span>Rounding</span><strong>{calculation.result.rounding?`${text(calculation.result.rounding.allowed)} allowed / ${text(calculation.result.rounding.blocked)} blocked`:"Not recorded"}</strong></div></div>
          {window?<><div className="evidence-subhead">Selected derived interval</div><div className="detail-list"><div><span>From / to</span><strong>{dateTimeAt(window.start_at)}<br/>{dateTimeAt(window.end_at)}</strong></div>
            <div><span>Usable time</span><strong>{window.usable_minutes} min</strong></div><div><span>Tracks</span><strong>{window.track_ids.join(", ")}</strong></div></div>
            <div className="evidence-subhead">COA context</div>{coveringCoa.length?coveringCoa.map(x=><div className="nearby-fact" key={x.id}><strong>{x.external_id}</strong><span>{x.track_id} · {timeAt(x.start_at)}–{timeAt(x.end_at)}</span><small>Source {x.source_mode} · revision {x.source_revision??"unknown"}</small></div>):<p className="muted">No individual COA record intersects this interval. Inspect the calculation policy and source bundle before interpreting the saved window.</p>}
            <div className="evidence-subhead">Nearest recorded source intervals</div><p className="quiet-note">Sorted by distance to either window boundary. Proximity alone does not establish which fact set the boundary.</p>
            {nearby.length?nearby.map(x=><button key={x.key} className={`nearby-fact nearby-button ${focus?.id===x.id?"nearby-active":""}`} onClick={()=>setFocus({kind:x.kind,id:x.id})}>
              <strong>{x.label}</strong><span>{x.track} · {timeAt(x.start)}–{timeAt(x.end)}</span><small>{x.layer} · {gapMinutes(x,window)} min from nearest boundary</small></button>):<p className="muted">No source interval on the selected tracks was recorded.</p>}
          </>:<p className="muted">No capacity window was returned for this calculation.</p>}
          {!!view.facts.commitments?.length&&<div className="inline-note">Approved commitments are shown as separate scheduling constraints. A capacity window alone is not a validated block proposal.</div>}
        </div>}
      </aside></div><p className="planning-disclaimer">Only saved backend calculations are labeled available. Source facts, forecast uncertainty, and human operational authority remain separate.</p></>}
  </div>;
}
