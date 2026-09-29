"use client";

import {useCallback,useEffect,useState} from "react";
import {api,dateTimeAt,messageFor,shortId} from "@/lib/api";
import {useSession} from "@/lib/session";
import {DataState} from "@/components/data-state";
import {StatusBadge} from "@/components/status-badge";

type SystemStatus={
  status:"READY"|"DEGRADED";checked_at:string;
  api:{status:string};database:{status:string;engine:string;migration_revision:string};
  worker:{status:"RESPONSIVE"|"STALE"|"ABSENT";responsive_instances:number;last_seen_at:string|null;max_age_seconds:number};
  queue:{preparation:number;queued_runs:number;running_runs:number};
  access:{users:Array<{id:string;name:string;role:string;department:string|null;active:boolean}>;provisioning:string};
  session:{kind:string;expires_at:string|null;user_id:string};railway_control:false;
};

export default function SystemPage(){
  const session=useSession();const role=session.value?.user.role;
  const [state,setState]=useState<SystemStatus|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState<string|null>(null);
  const refresh=useCallback(async()=>{setLoading(true);setError(null);try{setState(await api<SystemStatus>("/admin/system"))}catch(cause){setState(null);setError(messageFor(cause))}finally{setLoading(false)}},[]);
  useEffect(()=>{if(role==="ADMIN")void refresh()},[role,refresh]);
  return <div className="content-flow system-page"><div className="page-heading"><div><span className="eyebrow">OBSERVED DEPENDENCIES · ACCESS SCOPE · QUEUED WORK</span><h1>Access &amp; System Health</h1><p>Current API, database and worker evidence for this R-MAPS instance.</p></div>{role==="ADMIN"&&<div className="page-actions"><button className="button button-outline" type="button" onClick={()=>void refresh()} disabled={loading}>{loading?"Checking…":"Refresh status"}</button></div>}</div>
    {role!=="ADMIN"?<div className="panel"><DataState title="Administrator access required" detail="System health and the provisioned user roster are restricted to the ADMIN role."/></div>:
      error?<div className="panel"><div className="inline-alert" role="alert">{error}</div><DataState title="System status unavailable" detail="The API or database did not return current status. No component is presented as healthy until the request succeeds." action="Retry" onAction={()=>void refresh()}/></div>:
      !state?<div className="panel"><DataState title="Checking system state" detail="Reading the API, schema revision, worker heartbeat, queue and access roster…"/></div>:<>
        <div className="system-strip panel"><div><span>Overall</span><StatusBadge value={state.status}/><small>Checked {dateTimeAt(state.checked_at)}</small></div><div><span>API</span><StatusBadge value={state.api.status}/><small>Railway control: disabled</small></div><div><span>Database</span><StatusBadge value={state.database.status}/><small>{state.database.engine} · migration {state.database.migration_revision}</small></div><div><span>Planning worker</span><StatusBadge value={state.worker.status}/><small>{state.worker.responsive_instances} responsive instance(s)</small></div></div>
        <div className="system-grid"><section className="panel"><div className="panel-header"><div><h2>Worker and queue</h2><p>A heartbeat within {state.worker.max_age_seconds} seconds is required for responsive status</p></div><StatusBadge value={state.worker.status}/></div><div className="system-worker"><div><span>Last worker heartbeat</span><strong>{state.worker.last_seen_at?dateTimeAt(state.worker.last_seen_at):"No active worker reported"}</strong></div><div><span>Session preparation queued</span><strong>{state.queue.preparation}</strong></div><div><span>Planning runs queued</span><strong>{state.queue.queued_runs}</strong></div><div><span>Planning runs running</span><strong>{state.queue.running_runs}</strong></div></div><p className="system-note">A responsive heartbeat confirms the worker process recently reached PostgreSQL. It does not prove that a particular job will succeed. Stale or absent status remains visible even when the API and database respond.</p></section>
        <section className="panel"><div className="panel-header"><div><h2>Current access session</h2><p>Role, authentication mode and expiry for this administrator</p></div></div><div className="system-worker"><div><span>Signed-in role</span><strong>{session.value?.user.role??"UNKNOWN"}</strong></div><div><span>Current user</span><strong>{session.value?.user.name??"UNKNOWN"} · {shortId(state.session.user_id)}</strong></div><div><span>Authentication</span><strong>{state.session.kind.replaceAll("_"," ")}</strong></div><div><span>Expires</span><strong>{state.session.expires_at?dateTimeAt(state.session.expires_at):"Not returned for bearer access"}</strong></div></div><p className="system-note">Credentials and session secrets are never shown. Provisioning remains outside this administration screen.</p></section></div>
        <section className="panel"><div className="panel-header"><div><h2>Provisioned roles</h2><p>Read-only roster from the access table; credentials and hashes are excluded</p></div><strong>{state.access.users.length} users</strong></div><div className="system-table-scroll"><table className="system-table"><thead><tr><th>Name</th><th>Role</th><th>Department</th><th>Status</th><th>Identity</th></tr></thead><tbody>{state.access.users.map(user=><tr key={user.id}><td><strong>{user.name}</strong></td><td>{user.role}</td><td>{user.department??"Corridor-wide"}</td><td><StatusBadge value={user.active?"ACTIVE":"INACTIVE"}/></td><td>{shortId(user.id)}</td></tr>)}</tbody></table></div><p className="system-note">Provisioning method: {state.access.provisioning.replaceAll("_"," ")}. Role changes need the approved credential-management process and are not performed here.</p></section>
      </>}
  </div>;
}
