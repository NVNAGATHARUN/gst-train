"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError, dateAt, dateTimeAt, messageFor, shortId } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useCase } from "@/components/app-shell";
import { DataState } from "@/components/data-state";
import { DepartmentBadge, StatusBadge } from "@/components/status-badge";
import type { Department, MaintenanceRequest, Page, RequirementPayload, WorkspaceView } from "@/lib/types";

type Asset = {id:string;department:Department;footprint:string[];asset_type:string};
type AssetsResponse = {items:Asset[]};
type FilterDepartment = "ALL" | Department;

function localInputToIso(value: string): string {
  // This railway planning form is expressed in IST, independent of browser timezone.
  const date = new Date(`${value}:00+05:30`);
  if (Number.isNaN(date.getTime())) throw new Error("Enter a valid date and time.");
  return date.toISOString();
}

function RequestForm({ assets, department, csrf, onDone, onClose }: {
  assets: Asset[]; department: Department; csrf: string; onDone: () => void; onClose: () => void;
}) {
  const [assetId, setAssetId] = useState(assets[0]?.id ?? "");
  const [issue, setIssue] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState(3);
  const [urgency, setUrgency] = useState(3);
  const [workMinutes, setWorkMinutes] = useState(60);
  const [setupMinutes, setSetupMinutes] = useState(10);
  const [restoreMinutes, setRestoreMinutes] = useState(10);
  const [earliest, setEarliest] = useState("");
  const [deadline, setDeadline] = useState("");
  const [mandatory, setMandatory] = useState(false);
  const [lineBlock, setLineBlock] = useState(true);
  const [powerBlock, setPowerBlock] = useState(false);
  const [powerState, setPowerState] = useState("UNKNOWN");
  const [signallingState, setSignallingState] = useState("UNKNOWN");
  const [resourceType, setResourceType] = useState("");
  const [resourceQuantity, setResourceQuantity] = useState(1);
  const [resourceQualification, setResourceQualification] = useState("");
  const [isolationZone, setIsolationZone] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const asset = assets.find(a => a.id === assetId);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(null); setBusy(true);
    try {
      if (!asset) throw new Error("Select a valid department asset.");
      if (powerBlock && !isolationZone.trim()) throw new Error("Enter the known isolation zone for a power block.");
      const payload = {
        department, asset_id: asset.id, footprint: asset.footprint,
        issue_type: issue.trim(), description: description.trim(), severity, urgency,
        work_minutes: workMinutes, setup_minutes: setupMinutes, restore_minutes: restoreMinutes,
        earliest_at: localInputToIso(earliest), deadline_at: localInputToIso(deadline),
        mandatory, block_required: lineBlock, power_block_required: powerBlock,
        isolation_zone: powerBlock ? isolationZone.trim() : null,
        power_state: powerBlock ? "OFF" : powerState, signalling_state: signallingState,
        requirements: resourceType.trim() ? [{type:resourceType.trim(),quantity:resourceQuantity,qualification:resourceQualification.trim()||null}] : [],
        predecessors: [], source_mode: "SIMULATED",
      };
      await api("/maintenance-requests", {method:"POST", body:payload, csrf});
      onDone();
    } catch (cause) { setError(messageFor(cause)); }
    finally { setBusy(false); }
  }
  return <section className="panel request-form-panel" aria-labelledby="request-form-title">
    <div className="panel-header"><div><h2 id="request-form-title">New simulated requirement</h2><p>{department} · department submission</p></div>
      <button type="button" className="button button-text" onClick={onClose}>Close</button></div>
    <form className="request-form-grid" onSubmit={submit}>
      <label className="field">Asset<select value={assetId} onChange={event => setAssetId(event.target.value)} required>
        {assets.map(item => <option key={item.id} value={item.id}>{item.id} · {item.asset_type}</option>)}</select></label>
      <div className="field"><span>Track footprint</span><div className="field-readonly">{asset?.footprint.join(", ") || "No asset selected"}</div></div>
      <label className="field">Work category<input value={issue} onChange={event => setIssue(event.target.value)} maxLength={60} required /></label>
      <label className="field">Description<input value={description} onChange={event => setDescription(event.target.value)} maxLength={4000} /></label>
      <label className="field">Severity (1–5)<input type="number" min={1} max={5} value={severity} onChange={event => setSeverity(Number(event.target.value))} required /></label>
      <label className="field">Urgency (1–5)<input type="number" min={1} max={5} value={urgency} onChange={event => setUrgency(Number(event.target.value))} required /></label>
      <label className="field">Work minutes<input type="number" min={1} max={10080} value={workMinutes} onChange={event => setWorkMinutes(Number(event.target.value))} required /></label>
      <label className="field">Setup minutes<input type="number" min={0} max={1440} value={setupMinutes} onChange={event => setSetupMinutes(Number(event.target.value))} required /></label>
      <label className="field">Restoration minutes<input type="number" min={0} max={1440} value={restoreMinutes} onChange={event => setRestoreMinutes(Number(event.target.value))} required /></label>
      <label className="field">Earliest start (IST)<input type="datetime-local" value={earliest} onChange={event => setEarliest(event.target.value)} required /></label>
      <label className="field">Deadline (IST)<input type="datetime-local" value={deadline} onChange={event => setDeadline(event.target.value)} required /></label>
      <label className="field">Isolation zone, if required<input value={isolationZone} onChange={event => setIsolationZone(event.target.value)} disabled={!powerBlock} /></label>
      <label className="field">Power state<select value={powerBlock ? "OFF" : powerState} disabled={powerBlock} onChange={event => setPowerState(event.target.value)}><option value="UNKNOWN">Unknown</option><option value="ANY">Either state permitted</option><option value="ON">Power on required</option><option value="OFF">Power off required</option></select></label>
      <label className="field">S&amp;T state<select value={signallingState} onChange={event => setSignallingState(event.target.value)}><option value="UNKNOWN">Unknown</option><option value="ANY">Either state permitted</option><option value="CONNECTED">Connected required</option><option value="DISCONNECTED">Disconnection required</option></select></label>
      <label className="field">Resource type<input value={resourceType} onChange={event => setResourceType(event.target.value)} maxLength={60} placeholder="If known" /></label>
      <label className="field">Resource quantity<input type="number" min={1} max={100} value={resourceQuantity} onChange={event => setResourceQuantity(Number(event.target.value))} disabled={!resourceType.trim()} /></label>
      <label className="field">Resource qualification<input value={resourceQualification} onChange={event => setResourceQualification(event.target.value)} maxLength={60} disabled={!resourceType.trim()} placeholder="If required" /></label>
      <div className="request-form-options"><label><input type="checkbox" checked={mandatory} onChange={event => setMandatory(event.target.checked)} /> Mandatory</label>
        <label><input type="checkbox" checked={lineBlock} onChange={event => setLineBlock(event.target.checked)} /> Line block required</label>
        <label><input type="checkbox" checked={powerBlock} onChange={event => setPowerBlock(event.target.checked)} /> Power block required</label></div>
      <div className="request-form-footer"><span className="muted">Unknown railway prerequisites remain explicit. The request must pass backend validation before planning.</span>
        {error && <div className="inline-alert" role="alert">{error}</div>}
        <button className="button button-primary" type="submit" disabled={busy || !asset}>{busy ? "Saving…" : "Save requirement"}</button></div>
    </form>
  </section>;
}

function AccessDetails({ data }: {data: RequirementPayload}) {
  return <div className="detail-list">
    <div><span>Line block</span><strong>{data.block_required ? "Required" : "Not required"}</strong></div>
    <div><span>Power block</span><strong>{data.power_block_required ? "Required" : "Not required"}</strong></div>
    <div><span>Isolation zone</span><strong>{data.isolation_zone || "Not provided"}</strong></div>
    <div><span>S&amp;T disconnection</span><strong>{data.signalling_state === "DISCONNECTED" ? "Required" : data.signalling_state === "UNKNOWN" ? "Unknown" : "Not required"}</strong></div>
  </div>;
}

export default function MaintenancePage() {
  const { value: session, invalidate } = useSession();
  const selectedCase = useCase();
  const [rows, setRows] = useState<MaintenanceRequest[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceView | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [department, setDepartment] = useState<FilterDepartment>("ALL");
  const [status, setStatus] = useState("ALL");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [reload, setReload] = useState(0);
  const canCreate = session?.user.role === "DEPARTMENT" && !!session.user.department;
  const load = useCallback(async (offset = 0) => {
    setLoading(true); setError(null);
    try {
      const page = await api<Page<MaintenanceRequest>>(`/maintenance-requests?limit=100&offset=${offset}`);
      setRows(previous => offset === 0 ? page.items : [...previous, ...page.items]);
      setNextOffset(page.next_offset ?? null);
    } catch (cause) { if (cause instanceof ApiError && cause.status === 401) invalidate(); setError(messageFor(cause)); }
    finally { setLoading(false); }
  }, [invalidate]);
  useEffect(() => { void load(); }, [load, reload]);
  useEffect(() => {
    if (!selectedCase.snapshotId || session?.user.role === "DEPARTMENT") { setWorkspace(null); return; }
    const controller = new AbortController();
    const revision = selectedCase.revisionId ? `?plan_revision_id=${encodeURIComponent(selectedCase.revisionId)}` : "";
    void api<WorkspaceView>(`/snapshots/${selectedCase.snapshotId}/workspace${revision}`, {signal:controller.signal})
      .then(setWorkspace).catch(() => { if (!controller.signal.aborted) setWorkspace(null); });
    return () => controller.abort();
  }, [selectedCase.snapshotId, selectedCase.revisionId, session?.user.role]);
  useEffect(() => {
    if (!canCreate) return;
    void api<AssetsResponse>("/assets").then(data => setAssets(data.items)).catch(() => setAssets([]));
  }, [canCreate]);
  const visible = rows.filter(row => {
    if (department !== "ALL" && row.data.department !== department) return false;
    if (status !== "ALL" && row.status !== status) return false;
    const text = [row.id, row.data.issue_type, row.data.asset_id, ...row.data.footprint, row.data.description].join(" ").toLowerCase();
    if (search && !text.includes(search.toLowerCase())) return false;
    return true;
  });
  const active = rows.find(row => row.id === selected) ?? null;
  const activeDemand = workspace?.demands.find(d => d.request_id === selected);
  const [transitionBusy,setTransitionBusy]=useState(false);
  const [transitionNotice,setTransitionNotice]=useState<string|null>(null);
  async function transitionRequest(action:'VALIDATE'|'SUBMIT'){
    if(!active||!session||!canCreate||active.data.department!==session.user.department)return;
    setTransitionBusy(true);setError(null);setTransitionNotice(null);
    try{await api(`/maintenance-requests/${active.id}/transitions`,{method:'POST',csrf:session.csrf_token,body:{action,expected_revision:active.revision,reason:action==='VALIDATE'?'Department reviewed the simulated requirement':'Department submitted requirement for planning'}});
      await load();setTransitionNotice(action==='SUBMIT'?'Submitted. This request is eligible for capture in a new planning snapshot. Existing plans remain unchanged.':'Requirement validated. Submit it to make it eligible for planning.');
    }catch(cause){setError(messageFor(cause));}finally{setTransitionBusy(false);}
  }
  const states = Array.from(new Set(rows.map(row => row.status))).sort();
  return <div className="content-flow">
    <div className="page-heading"><div><span className="eyebrow">MAINTENANCE INTELLIGENCE</span><h1>Maintenance requirements</h1>
      <p>Department demand, deadlines, access and readiness in one register.</p></div>
      <div className="page-actions">{canCreate && <button className="button button-primary" onClick={() => setShowForm(true)}>+ Add requirement</button>}
        <button className="button button-outline" onClick={() => void load()} disabled={loading}>Refresh</button></div></div>
    {showForm && canCreate && <RequestForm department={session!.user.department!} assets={assets} csrf={session!.csrf_token}
      onDone={() => {setShowForm(false);setReload(x=>x+1);}} onClose={() => setShowForm(false)} />}
    {selectedCase.snapshotId && <div className="inline-note">Planning context: snapshot <span className="mono">{shortId(selectedCase.snapshotId)}</span>.
      {workspace ? " Readiness and priority come from that saved snapshot and selected proposal." : " Snapshot evidence unavailable here; readiness is not assessed."}</div>}
    <div className="panel maintenance-panel"><div className="maintenance-controls">
      <label className="field">Department<select value={department} onChange={event => setDepartment(event.target.value as FilterDepartment)}>
        <option value="ALL">All departments</option><option value="ENGINEERING">Engineering</option><option value="TRD">TRD</option><option value="SNT">S&amp;T</option></select></label>
      <label className="field">Lifecycle<select value={status} onChange={event => setStatus(event.target.value)}>
        <option value="ALL">All states</option>{states.map(value => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label>
      <label className="field maintenance-search">Find request<input type="search" placeholder="ID, work, asset or track" value={search} onChange={event => setSearch(event.target.value)} /></label>
      <span className="controls-count">{visible.length} shown{nextOffset !== null ? " · more available" : ""}</span>
    </div>
    {error && <div className="inline-alert" role="alert">{error}</div>}
    {loading && rows.length === 0 ? <DataState title="Loading requirements" detail="Reading the current department register…" /> :
      rows.length === 0 ? <DataState title="No maintenance requirements" detail="Requests will appear here after a department creates or imports them." /> :
      <div className="maintenance-table-scroll"><table className="maintenance-table"><caption className="sr-only">Saved maintenance requirements</caption>
        <thead><tr><th>Requirement</th><th>Dept.</th><th>Asset / work</th><th>Track</th><th>Package</th><th>Deadline</th><th>Priority</th><th>Readiness</th><th>Lifecycle</th></tr></thead>
        <tbody>{visible.map(row => {
          const demand = workspace?.demands.find(d => d.request_id === row.id);
          const duration = row.data.setup_minutes + row.data.work_minutes + row.data.restore_minutes;
          return <tr key={row.id} className={selected === row.id ? "selected-row" : ""}>
            <td><button type="button" className="table-select" onClick={() => setSelected(row.id)} aria-label={`Inspect ${row.id}`}>
              <strong className="mono">{shortId(row.id)}</strong><small>Rev {row.revision} · {row.data.source_mode}</small></button></td>
            <td><DepartmentBadge department={row.data.department} /></td>
            <td><strong>{row.data.issue_type}</strong><small>{row.data.asset_id}</small></td>
            <td className="mono">{row.data.footprint.join(", ")}</td>
            <td className="tabular">{duration} min<small>{row.data.setup_minutes} + {row.data.work_minutes} + {row.data.restore_minutes}</small></td>
            <td>{dateAt(row.data.deadline_at)}{row.data.mandatory && <small className="text-urgent">Mandatory</small>}</td>
            <td>{demand?.priority ? <><StatusBadge value={demand.priority.priority_band} /><small>Rule · {(demand.priority.score_basis_points / 100).toFixed(1)}/100</small></> : <span className="muted">Not assessed</span>}</td>
            <td><StatusBadge value={demand?.readiness.status ?? "NOT_ASSESSED"} /></td>
            <td><StatusBadge value={row.status} /></td>
          </tr>;
        })}</tbody></table></div>}
    {visible.length === 0 && rows.length > 0 && <DataState title="No matching requirements" detail="Change the filters to see other saved requests." />}
    {nextOffset !== null && <div className="load-more"><button type="button" className="button button-outline" disabled={loading} onClick={() => void load(nextOffset)}>Load more</button></div>}
    </div>
    {active && <section className="panel maintenance-detail" aria-label="Requirement detail"><div className="panel-header">
      <div><h2>{active.data.issue_type} <span className="mono muted">· {shortId(active.id)}</span></h2>
        <p>{active.data.asset_id} · {active.data.footprint.join(", ")} · revision {active.revision}</p></div>
      <button type="button" className="button button-text" onClick={() => setSelected(null)}>Close</button></div>
      <div className="panel-header"><div><StatusBadge value={active.status}/><p>{active.status==='RAISED'?'Review and validate this requirement, then submit it for planning.':active.status==='VALIDATED'?'Validated requirement: submit it for planning.':active.status==='PENDING_PLANNING'?'Submitted demand. A new snapshot is required to include it in a block plan.':'Recorded lifecycle state; planning and execution evidence remain separate.'}</p>{transitionNotice&&<p role="status">{transitionNotice}</p>}</div>
        {canCreate&&active.data.department===session?.user.department&&['RAISED','VALIDATED'].includes(active.status)&&<button className="button button-primary" disabled={transitionBusy} onClick={()=>void transitionRequest(active.status==='RAISED'?'VALIDATE':'SUBMIT')}>{transitionBusy?'Saving…':active.status==='RAISED'?'Validate requirement':'Submit for planning'}</button>}</div>
      <div className="maintenance-detail-grid"><div><h3>Requirement and timing</h3><p>{active.data.description || "No description provided."}</p>
        <div className="detail-list"><div><span>Earliest start</span><strong>{dateTimeAt(active.data.earliest_at)}</strong></div>
          <div><span>Deadline</span><strong>{dateTimeAt(active.data.deadline_at)}</strong></div>
          <div><span>Setup / work / restoration</span><strong>{active.data.setup_minutes} / {active.data.work_minutes} / {active.data.restore_minutes} min</strong></div>
          <div><span>Predecessors</span><strong>{active.data.predecessors.join(", ") || "None declared"}</strong></div></div></div>
        <div><h3>Railway access</h3><AccessDetails data={active.data} /><p className="quiet-note">Requirements are declarations; operating authorization is separate.</p></div>
        <div><h3>Planning evidence</h3><div className="detail-list">
          <div><span>Scheduling outcome</span><strong>{activeDemand?.scheduling_outcome.replaceAll("_", " ") ?? "Not planned in selected context"}</strong></div>
          <div><span>Readiness</span><strong>{activeDemand?.readiness.status.replaceAll("_", " ") ?? "Not assessed"}</strong></div>
          <div><span>Priority</span><strong>{activeDemand?.priority ? `Rule ${activeDemand.priority.score_basis_points / 100}/100` : "Not assessed"}</strong></div>
          <div><span>Resource requirements</span><strong>{active.data.requirements.map(r => `${r.quantity} × ${r.type}`).join(", ") || "None declared"}</strong></div>
        </div>{activeDemand?.readiness.reasons.length ? <p className="quiet-note">{activeDemand.readiness.reasons.join(" · ")}</p> : null}
        {!canCreate&&<Link className="button button-outline inline-link" href="/planning">Open Planning Workspace</Link>}</div></div>
    </section>}
  </div>;
}
