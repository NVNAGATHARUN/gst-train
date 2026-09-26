"use client";

import {useEffect,useMemo,useRef,useState} from "react";
import {dateAt,dateTimeAt,timeAt} from "@/lib/api";
import {initialLayers,intervalStyle,layerNames,timelineItems} from "@/lib/timeline";
import {stackIntervals,timelineTicks} from "@/lib/timeline-layout";
import type {Focus,Layer} from "@/lib/timeline";
import type {WorkspaceView} from "@/lib/types";
import {RailIcon} from "./rail-icon";

const allLayers:Layer[]=["train","freight","coa","restriction","commitment","released","capacity","candidate","proposal"];
const layerGroup=(layer:Layer)=>["capacity","candidate"].includes(layer)?"Computed":layer==="proposal"?"Proposal":"Source";

export function TimeTrackTimeline({view,focus,onFocus,title="Corridor planning diagram",layers:allowed=allLayers,selectedTrack,onTrackChange,scale,onScaleChange,scrollOffset,onScrollOffsetChange}:{
  view:WorkspaceView;focus:Focus|null;onFocus:(focus:Focus)=>void;title?:string;layers?:Layer[];
  selectedTrack?:string;onTrackChange?:(track:string)=>void;
  scale?:number;onScaleChange?:(scale:number)=>void;
  scrollOffset?:number;onScrollOffsetChange?:(offset:number)=>void;
}){
  const [visibility,setVisibility]=useState(initialLayers);
  const [internalTrack,setInternalTrack]=useState("ALL");
  const [internalZoom,setInternalZoom]=useState(1);
  const zoom=scale??internalZoom;
  const setZoom=(value:number)=>onScaleChange?onScaleChange(value):setInternalZoom(value);
  const [hideEmpty,setHideEmpty]=useState(false);
  const scrollRef=useRef<HTMLDivElement>(null);
  useEffect(()=>{if(scrollOffset!==undefined&&scrollRef.current&&Math.abs(scrollRef.current.scrollLeft-scrollOffset)>1)scrollRef.current.scrollLeft=scrollOffset},[scrollOffset,zoom]);
  const requestedTrack=selectedTrack??internalTrack;
  const track=requestedTrack==="ALL"||view.snapshot.track_ids.includes(requestedTrack)?requestedTrack:"ALL";
  const chooseTrack=(value:string)=>{if(onTrackChange)onTrackChange(value);else setInternalTrack(value)};
  const items=useMemo(()=>timelineItems(view),[view]);
  const start=Date.parse(view.snapshot.horizon_start),end=Date.parse(view.snapshot.horizon_end);
  const tracks=track==="ALL"?view.snapshot.track_ids:view.snapshot.track_ids.filter(x=>x===track);
  const ticks=timelineTicks(start,end,zoom===1?4:8);
  const shownItems=items.filter(item=>tracks.includes(item.track)&&allowed.includes(item.layer)&&visibility[item.layer]);
  const groups=tracks.map(current=>({track:current,lanes:allowed.filter(layer=>visibility[layer]).map(layer=>({
    layer,...stackIntervals(items.filter(item=>item.track===current&&item.layer===layer),start,end),
  })).filter(lane=>!hideEmpty||lane.entries.length>0)}));
  function emptyLabel(layer:Layer){
    if(layer==="capacity")return view.availability.length?"No capacity returned on this track":"Capacity not calculated in this context";
    if(layer==="candidate")return view.coordination?"No candidates on this track":"Candidates not generated";
    if(layer==="proposal")return view.selected_run||view.selected_revision?"No proposed blocks on this track":"No plan selected";
    return "No records in this snapshot · completeness not implied";
  }
  return <section className="panel timeline-panel" aria-label="Time and track planning timeline">
    <div className="panel-header timeline-heading"><div className="timeline-title"><RailIcon name="corridor"/><div><h2>{title}</h2><p>{dateTimeAt(view.snapshot.horizon_start)} — {dateTimeAt(view.snapshot.horizon_end)}</p></div></div>
      <div className="timeline-tools"><label className="field small-field"><span className="sr-only">Track</span><select aria-label="Timeline track" value={track} onChange={e=>chooseTrack(e.target.value)}><option value="ALL">All tracks</option>{view.snapshot.track_ids.map(x=><option key={x}>{x}</option>)}</select></label>
        <div className="segmented-control" aria-label="Timeline scale">{[1,2,4].map(scale=><button key={scale} type="button" aria-pressed={zoom===scale} onClick={()=>setZoom(scale)}>{scale===1?"Fit":`${scale}×`}</button>)}</div></div></div>
    <div className="timeline-legend">{allowed.map(layer=><label key={layer} className={`layer-toggle legend-${layer}`}><input type="checkbox" checked={visibility[layer]} onChange={e=>setVisibility({...visibility,[layer]:e.target.checked})}/><span className={`legend-swatch block-${layer}`} aria-hidden="true"/>{layerNames[layer]}</label>)}</div>
    <div className="timeline-subtoolbar"><span><b>{view.snapshot.source_scope}</b> · Source / computed / proposal layers</span><label><input type="checkbox" checked={hideEmpty} onChange={event=>setHideEmpty(event.target.checked)}/>Hide empty rows</label></div>
    {ticks.length===0?<div className="inline-alert" role="alert">The saved horizon is invalid. Timeline cannot be drawn.</div>:
    <div className="timeline-scroll" ref={scrollRef} onScroll={event=>onScrollOffsetChange?.(event.currentTarget.scrollLeft)} tabIndex={0} role="region" aria-label="Scrollable time–track diagram; use arrow keys to scroll"><div className="timeline-inner" style={{width:`${zoom*100}%`}}><div className="timeline-axis"><span>SECTION / TRACK</span><div>{ticks.map((tick,i)=><span key={i} style={{left:`${100*i/(ticks.length-1)}%`}}><b>{timeAt(tick)}</b><small>{dateAt(tick).replace(/ \d{4}$/,"")}</small></span>)}</div></div>
      {groups.map(group=><div className="track-group" key={group.track}><div className="track-heading"><span className="track-node" aria-hidden="true"/><strong>{group.track}</strong><small>{view.facts.network.find(x=>x.kind==="track"&&x.id===group.track)?.payload.section_id as string??"Section not recorded"}</small><span className="track-heading-note">Half-open intervals · IST</span></div>
        {group.lanes.map(({layer,entries,rows})=><div className="timeline-lane" key={layer}><span className="lane-label"><span>{layerNames[layer]}</span><small>{layerGroup(layer)} · {entries.length}</small></span><div className="lane-grid" style={{height:Math.max(42,rows*30+10)}} role="group" aria-label={`${group.track} ${layerNames[layer]}`}>
          {entries.length===0&&<span className="empty-lane-label">{emptyLabel(layer)}</span>}
          {entries.map(({item,row})=>{const style=intervalStyle(item,start,end);return style&&<button key={item.key} type="button"
            className={`timeline-block block-${layer} ${focus?.kind===item.kind&&focus.id===item.id?"timeline-block-selected":""}`}
            style={{...style,top:6+row*30}} onClick={()=>onFocus({kind:item.kind,id:item.id})} aria-pressed={focus?.kind===item.kind&&focus.id===item.id}
            title={`${item.label}: ${dateTimeAt(item.start)} to ${dateTimeAt(item.end)}`} aria-label={`${item.label} on ${item.track}, ${dateTimeAt(item.start)} to ${dateTimeAt(item.end)}`}>{item.label}</button>})}
        </div></div>)}
        {group.lanes.length===0&&<p className="timeline-empty">No visible rows. Enable a layer or turn off “Hide empty rows”.</p>}
      </div>)}
      {tracks.length===0&&<p className="timeline-empty">No track footprint recorded in this snapshot.</p>}
    </div></div>}
    <div className="timeline-foot"><span><strong>{shownItems.length}</strong> recorded track intervals in visible layers</span><span>Blank space is not evidence of free capacity.</span></div>
    <details className="interval-register"><summary>Interval register <span>Exact times & keyboard selection</span></summary><div className="interval-register-scroll"><table><caption className="sr-only">The same saved intervals as the selected timeline layers</caption><thead><tr><th scope="col">Evidence</th><th scope="col">Track</th><th scope="col">Layer</th><th scope="col">Start · IST</th><th scope="col">End · IST</th></tr></thead><tbody>{shownItems.map(item=><tr key={item.key}><td><button type="button" className="table-select" onClick={()=>onFocus({kind:item.kind,id:item.id})}>{item.label}</button></td><td>{item.track}</td><td>{layerNames[item.layer]}</td><td>{dateTimeAt(item.start)}</td><td>{dateTimeAt(item.end)}</td></tr>)}</tbody></table>{shownItems.length===0&&<p className="timeline-empty">No intervals in the visible layers.</p>}</div></details>
  </section>;
}
