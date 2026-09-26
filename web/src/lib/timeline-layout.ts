/** Presentation only: never derive capacity or change backend intervals here. */
export type TimedItem = {key:string; start:string; end:string};

export function stackIntervals<T extends TimedItem>(items:T[], start:number, end:number) {
  const visible=items.filter(item=>{
    const a=Date.parse(item.start), b=Date.parse(item.end);
    return Number.isFinite(a)&&Number.isFinite(b)&&b>a&&a<end&&b>start;
  }).sort((a,b)=>Date.parse(a.start)-Date.parse(b.start)||Date.parse(a.end)-Date.parse(b.end)||a.key.localeCompare(b.key));
  const laneEnds:number[]=[];
  const entries=visible.map(item=>{
    const left=Math.max(start,Date.parse(item.start));
    let row=laneEnds.findIndex(value=>value<=left);
    if(row<0)row=laneEnds.length;
    laneEnds[row]=Math.min(end,Date.parse(item.end));
    return {item,row};
  });
  return {entries, rows:Math.max(1,laneEnds.length)};
}

export function timelineTicks(start:number,end:number,segments=4):string[] {
  if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start)return [];
  return Array.from({length:segments+1},(_,index)=>new Date(start+(end-start)*index/segments).toISOString());
}
