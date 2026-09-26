"use client";

import {useCallback,useEffect,useState} from "react";
import {useCase} from "@/components/app-shell";
import {api,ApiError,messageFor} from "./api";
import {useSession} from "./session";
import type {Page,PlanningSession,RunIndexItem,SnapshotSummary,WorkspaceView} from "./types";

export function useWorkspaceEvidence(){
  const selection=useCase();
  const {invalidate}=useSession();
  const [snapshots,setSnapshots]=useState<SnapshotSummary[]>([]);
  const [runs,setRuns]=useState<RunIndexItem[]>([]);
  const [sessions,setSessions]=useState<PlanningSession[]>([]);
  const [chosenRun,setChosenRun]=useState<{snapshotId:string;runId:string}|null>(null);
  const [view,setView]=useState<WorkspaceView|null>(null);
  const [loading,setLoading]=useState(true),[viewLoading,setViewLoading]=useState(false);
  const [error,setError]=useState<string|null>(null),[version,setVersion]=useState(0);
  const refresh=useCallback(()=>setVersion(x=>x+1),[]);
  const snapshot=snapshots.find(x=>x.id===selection.snapshotId);
  const session=sessions.find(x=>x.id===selection.sessionId);
  const runId=selection.revisionId?null:
    chosenRun?.snapshotId===selection.snapshotId?chosenRun.runId:
    session?.runs.find(x=>x.planner_type==="CP_SAT")?.id??null;
  const selectSnapshot=(id:string|null)=>{selection.selectSnapshot(id);setChosenRun(null)};
  const selectSession=(id:string|null)=>{selection.selectSession(id);setChosenRun(null)};
  const selectRun=(id:string|null)=>{selection.selectRevision(null);setChosenRun(id&&selection.snapshotId?{snapshotId:selection.snapshotId,runId:id}:null)};
  useEffect(()=>{const controller=new AbortController();setLoading(true);
    void api<Page<SnapshotSummary>>("/workspace/snapshots?scenario=ANY&limit=100",{signal:controller.signal})
      .then(page=>setSnapshots(page.items)).catch(cause=>{if(!controller.signal.aborted){if(cause instanceof ApiError&&cause.status===401)invalidate();setError(messageFor(cause))}})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false)});
    return()=>controller.abort();
  },[version,invalidate]);
  useEffect(()=>{if(!selection.snapshotId){setRuns([]);setSessions([]);return}
    const controller=new AbortController(),id=encodeURIComponent(selection.snapshotId);
    void Promise.all([api<Page<RunIndexItem>>(`/workspace/runs?snapshot_id=${id}&limit=100`,{signal:controller.signal}),
      api<Page<PlanningSession>>(`/workspace/planning-sessions?snapshot_id=${id}&limit=100`,{signal:controller.signal})])
      .then(([r,s])=>{setRuns(r.items);setSessions(s.items)}).catch(cause=>{if(!controller.signal.aborted)setError(messageFor(cause))});
    return()=>controller.abort();
  },[selection.snapshotId,version]);
  useEffect(()=>{if(!selection.snapshotId){setView(null);return}const controller=new AbortController();setViewLoading(true);setError(null);
    const suffix=selection.revisionId?`?plan_revision_id=${encodeURIComponent(selection.revisionId)}`:runId?`?run_id=${encodeURIComponent(runId)}`:"";
    void api<WorkspaceView>(`/snapshots/${selection.snapshotId}/workspace${suffix}`,{signal:controller.signal})
      .then(setView).catch(cause=>{if(!controller.signal.aborted){setView(null);setError(messageFor(cause))}})
      .finally(()=>{if(!controller.signal.aborted)setViewLoading(false)});
    return()=>controller.abort();
  },[selection.snapshotId,selection.revisionId,runId,version]);
  useEffect(()=>{
    if(!session||["COMPLETED","FAILED","SUPERSEDED"].includes(session.status))return;
    const timer=setTimeout(()=>{void api<PlanningSession>(`/planning-sessions/${session.id}`).then(next=>{
      setSessions(previous=>previous.map(x=>x.id===next.id?next:x));
      if(["COMPLETED","FAILED","SUPERSEDED"].includes(next.status))refresh();
    }).catch(cause=>setError(messageFor(cause)))},2500);
    return()=>clearTimeout(timer);
  },[session,refresh]);
  return {selection,snapshots,runs,sessions,snapshot,session,runId,view,loading,viewLoading,error,
    setError,refresh,selectSnapshot,selectSession,selectRun};
}
