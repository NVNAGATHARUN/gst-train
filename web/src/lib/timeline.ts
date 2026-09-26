import type {WorkspaceView} from "./types";

export type Focus = {kind:"request"|"train"|"freight"|"coa"|"window"|"candidate"|"assignment"|"restriction"|"commitment"|"released";id:string};
export type Layer = "train"|"freight"|"coa"|"restriction"|"commitment"|"released"|"capacity"|"candidate"|"proposal";
export const layerNames:Record<Layer,string> = {train:"Confirmed trains",freight:"Freight forecast",coa:"COA declarations",restriction:"Restrictions",commitment:"Approved commitments",released:"Recorded possession",capacity:"Available capacity",candidate:"Candidates",proposal:"Proposed blocks"};
export const initialLayers:Record<Layer,boolean> = {train:true,freight:true,coa:true,restriction:true,commitment:true,released:true,capacity:true,candidate:false,proposal:true};
export type TimelineItem = {key:string;kind:Focus["kind"];id:string;track:string;start:string;end:string;label:string;layer:Layer};

export function intervalStyle(item:TimelineItem,start:number,end:number) {
  const left=Math.max(start,Date.parse(item.start));
  const right=Math.min(end,Date.parse(item.end));
  if(!Number.isFinite(left)||!Number.isFinite(right)||right<=left||end<=start)return null;
  return {left:`${100*(left-start)/(end-start)}%`,width:`${100*(right-left)/(end-start)}%`};
}
export function timelineItems(view:WorkspaceView):TimelineItem[] {
  const items:TimelineItem[]=[];
  const add=(kind:Focus["kind"],id:string,tracks:string[],start:string,end:string,label:string,layer:Layer)=>{
    tracks.forEach(track=>items.push({key:`${kind}:${id}:${track}`,kind,id,track,start,end,label,layer}));
  };
  view.facts.occupancy.forEach(x=>add("train",x.id,[x.track_id],x.enter_at,x.exit_at,x.train_id,"train"));
  view.facts.freight.forEach(x=>add("freight",x.id,[x.track_id],x.start_at,x.end_at,x.external_id,"freight"));
  view.facts.coa.forEach(x=>add("coa",x.id,[x.track_id],x.start_at,x.end_at,x.external_id,"coa"));
  view.facts.network.filter(x=>x.kind==="restriction").forEach(x=>{
    const p=x.payload;
    const tracks=Array.isArray(p.footprint)?p.footprint.filter((t):t is string=>typeof t==="string"):[];
    if(typeof p.start==="string"&&typeof p.end==="string")add("restriction",x.id,tracks,p.start,p.end,x.id,"restriction");
  });
  view.facts.commitments?.forEach((x,index)=>{
    const a=x.assignment as Record<string,unknown>|undefined;
    if(a&&typeof a.possession_start==="string"&&typeof a.possession_end==="string"&&Array.isArray(a.track_ids))
      add("commitment",typeof x.id==="string"?x.id:`commitment-${index}`,
        a.track_ids.filter((t):t is string=>typeof t==="string"),a.possession_start,a.possession_end,
        x.frozen===true?"Frozen work":"Approved commitment","commitment");
  });
  view.facts.released_possessions?.forEach((x,index)=>{
    const p=x.payload as Record<string,unknown>|undefined,r=x.result as Record<string,unknown>|undefined;
    const a=r?.assignment as Record<string,unknown>|undefined;
    if(p&&a&&typeof p.actual_possession_start==="string"&&typeof p.restored_at==="string"&&Array.isArray(a.track_ids))
      add("released",typeof x.id==="string"?x.id:`released-${index}`,
        a.track_ids.filter((t):t is string=>typeof t==="string"),p.actual_possession_start,p.restored_at,
        "Recorded possession","released");
  });
  view.availability.flatMap(x=>x.result.windows??[]).forEach(x=>add("window",x.id,x.track_ids,x.start_at,x.end_at,"Free capacity","capacity"));
  view.coordination?.result.candidates?.forEach(x=>add("candidate",x.id,x.track_ids,x.possession_start,x.possession_end,x.request_ids.length>1?`${x.request_ids.length} works`:"Candidate","candidate"));
  const plan=view.selected_revision?.content??view.selected_run?.result;
  plan?.assignments?.forEach(x=>add("assignment",x.id,x.track_ids,x.possession_start,x.possession_end,x.request_ids.length>1?`Integrated · ${x.request_ids.length}`:"Proposed block","proposal"));
  return items;
}
