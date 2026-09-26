"use client";
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {api,dateTimeAt,messageFor,shortId} from '@/lib/api';
import type {MaintenanceRequest,Page} from '@/lib/types';
import {DepartmentBadge,StatusBadge} from './status-badge';
export function LiveMaintenanceIntake({captured}:{captured:readonly {id:string;revision:number}[]}){
 const [rows,setRows]=useState<MaintenanceRequest[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState<string|null>(null),[version,setVersion]=useState(0),[readAt,setReadAt]=useState<string|null>(null);
 useEffect(()=>{const refresh=()=>setVersion(x=>x+1);window.addEventListener('focus',refresh);const timer=window.setInterval(refresh,30000);return()=>{window.removeEventListener('focus',refresh);window.clearInterval(timer)};},[]);
 useEffect(()=>{const controller=new AbortController();setLoading(true);setError(null);
  void (async()=>{const items:MaintenanceRequest[]=[];let offset:number|null=0;
   while(offset!==null){const result:Page<MaintenanceRequest>=await api(`/maintenance-requests?limit=200&offset=${offset}`,{signal:controller.signal});items.push(...result.items);offset=result.next_offset??null;}
   if(!controller.signal.aborted){setRows(items.filter(row=>['RAISED','VALIDATED','PENDING_PLANNING'].includes(row.status)));setReadAt(new Date().toISOString());}
  })().catch(cause=>{if(!controller.signal.aborted){setRows([]);setReadAt(null);setError(messageFor(cause))}}).finally(()=>{if(!controller.signal.aborted)setLoading(false)});
  return()=>controller.abort();
 },[version]);
 const matching=(row:MaintenanceRequest)=>captured.some(item=>item.id===row.id&&item.revision===row.revision);
 const uncaptured=rows.filter(row=>row.status==='PENDING_PLANNING'&&!matching(row));
 return <section className="panel" aria-label="Live maintenance intake"><div className="panel-header"><div><h2>Incoming maintenance requests · live intake</h2><p>Current request register, separate from the saved snapshot and computed plan. Refreshes every 30 seconds and when this window regains focus.</p></div><button className="button button-outline" disabled={loading} onClick={()=>setVersion(x=>x+1)}>Refresh incoming requests</button></div>
 {error?<div className="inline-alert" role="alert">{error}</div>:loading?<p className="quiet-note">Reading current requests…</p>:<><p className="quiet-note">{rows.length} active request(s) · {uncaptured.length} submitted revision(s) absent from the selected snapshot. Last read {readAt?dateTimeAt(readAt):'Unknown'}.</p><details className="interval-register"><summary>Review incoming requests</summary><div className="table-scroll"><table><caption>Live demand lifecycle; these rows are not scheduled results</caption><thead><tr><th scope="col">Request</th><th scope="col">Department</th><th scope="col">Work / tracks</th><th scope="col">Lifecycle</th><th scope="col">Next step</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td>{shortId(row.id)} · r{row.revision}</td><td><DepartmentBadge department={row.data.department}/></td><td>{row.data.issue_type} · {row.data.footprint.join(', ')}</td><td><StatusBadge value={row.status}/></td><td>{row.status==='RAISED'?'Department must validate and submit':row.status==='VALIDATED'?'Department must submit':matching(row)?'Captured; inspect snapshot planning evidence':'Capture a new snapshot with this submitted revision'}</td></tr>)}</tbody></table></div>{!rows.length&&<p className="quiet-note">No active maintenance requests returned by the backend.</p>}</details></>}
 <div className="panel-header"><p>New demand does not alter an existing immutable snapshot. Eligibility also depends on selected tracks, horizon and prerequisites.</p><Link href="/maintenance">Open live request register →</Link></div></section>;
}
