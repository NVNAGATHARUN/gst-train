import {shortId,timeAt} from "@/lib/api";
import type {Candidate} from "@/lib/types";
import {DepartmentBadge} from "./status-badge";

export function TaskStages({candidate}:{candidate:Candidate}) {
  const start=Date.parse(candidate.possession_start),end=Date.parse(candidate.possession_end);
  return <div className="task-stages">{candidate.tasks.map(task=>{
    const stages=[{label:"Setup",start:task.setup_start,end:task.setup_end,key:"setup"},{label:"Work",start:task.work_start,end:task.work_end,key:"work"},{label:"Restoration",start:task.restore_start,end:task.restore_end,key:"restore"}];
    return <div className="task-stage-row" key={task.request_id}><div className="task-stage-title"><DepartmentBadge department={task.department}/><strong>{task.issue_type}</strong><span className="mono" title={task.request_id}>{shortId(task.request_id)}</span></div>
      {end>start&&<div className="task-stage-track" aria-hidden="true">{stages.map(stage=>{const left=Math.max(start,Date.parse(stage.start)),right=Math.min(end,Date.parse(stage.end));return right>left?<span key={stage.key} className={`task-stage-${stage.key}`} style={{left:`${100*(left-start)/(end-start)}%`,width:`${100*(right-left)/(end-start)}%`}}/>:null})}</div>}
      <dl>{stages.map(stage=><div key={stage.key}><dt>{stage.label}</dt><dd>{timeAt(stage.start)}–{timeAt(stage.end)}</dd></div>)}</dl>
    </div>;
  })}<p className="quiet-note">Task intervals use the same possession scale. Times in IST.</p></div>;
}
