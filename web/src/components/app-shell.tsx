"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { canOpenPage } from "@/lib/role-workspace";
import { DataState } from "./data-state";
import { useSession } from "@/lib/session";
import { RailIcon, type IconName } from "./rail-icon";

export type CaseSelection = { snapshotId: string | null; sessionId: string | null; revisionId: string | null };
type CaseValue = CaseSelection & {
  selectSnapshot: (id: string | null) => void;
  selectSession: (id: string | null) => void;
  selectRevision: (id: string | null) => void;
};
const CaseContext = createContext<CaseValue | null>(null);
const emptyCase: CaseSelection = { snapshotId: null, sessionId: null, revisionId: null };

function CaseProvider({ userId, children }: {userId: string; children: React.ReactNode}) {
  const [selection, setSelection] = useState<CaseSelection>(emptyCase);
  useEffect(() => {
    try {
      const value = sessionStorage.getItem(`railsync-case:${userId}`);
      if (value) {
        const record = JSON.parse(value) as Partial<CaseSelection>;
        setSelection({ snapshotId: record.snapshotId ?? null, sessionId: record.sessionId ?? null,
          revisionId: record.revisionId ?? null });
      }
    } catch { setSelection(emptyCase); }
  }, [userId]);
  const update = useCallback((next: CaseSelection) => {
    setSelection(next);
    try { sessionStorage.setItem(`railsync-case:${userId}`, JSON.stringify(next)); } catch { /* Browser storage can be disabled. */ }
  }, [userId]);
  const value = useMemo<CaseValue>(() => ({...selection,
    selectSnapshot: (id) => update({ snapshotId: id, sessionId: null, revisionId: null }),
    selectSession: (id) => update({ ...selection, sessionId: id, revisionId: null }),
    selectRevision: (id) => update({ ...selection, revisionId: id }),
  }), [selection, update]);
  return <CaseContext.Provider value={value}>{children}</CaseContext.Provider>;
}

export function useCase() {
  const value = useContext(CaseContext);
  if (!value) throw new Error("CaseProvider is missing");
  return value;
}

function RMapsMark() { return <span className="brand-mark"><RailIcon name="rail" size={26}/></span>; }

type NavItem = {label:string; href:string; icon:IconName; adminOnly?:boolean};
const navigation: {label:string; items:NavItem[]}[] = [
  {label:"Planning desk",items:[
    {label:"Overview",href:"/dashboard",icon:"overview"},
    {label:"Block planning",href:"/planning",icon:"plan"},
    {label:"Maintenance demand",href:"/maintenance",icon:"work"},
    {label:"Corridor & COA",href:"/corridor",icon:"corridor"},
  ]},
  {label:"Proposal & decision",items:[
    {label:"Planning sessions",href:"/optimization",icon:"solver"},
    {label:"Baseline comparison",href:"/evaluation",icon:"compare"},
    {label:"Independent validation",href:"/validation",icon:"validate"},
    {label:"Controller review",href:"/review",icon:"review"},
  ]},
  {label:"Delivery & records",items:[
    {label:"Weekly / monthly plan",href:"/schedules",icon:"calendar"},
    {label:"Replan & what-if",href:"/changes",icon:"change"},
    {label:"Execution & handback",href:"/execution",icon:"execution"},
    {label:"Reports & audit",href:"/reports",icon:"report"},
  ]},
  {label:"Data & configuration",items:[
    {label:"Data readiness",href:"/data-readiness",icon:"data"},
    {label:"Network & rules",href:"/admin",icon:"settings"},
    {label:"System health",href:"/system",icon:"health",adminOnly:true},
  ]},
];

function WorkShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { value, signOut } = useSession();
  const selection = useCase();
  const [signOutError, setSignOutError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const visibleNavigation = navigation.map(group=>({...group,items:group.items.filter(item=>canOpenPage(value?.user.role,item.href))})).filter(group=>group.items.length);
  const allowed = canOpenPage(value?.user.role,pathname);
  async function leaveSession(){
    try { await signOut(); router.replace("/login"); }
    catch { setSignOutError("Could not sign out. Retry before leaving this device."); }
  }
  return <div className={`app-root ${menuOpen?"navigation-open":""}`}>
    <a className="skip-link" href="#main-content">Skip to workspace</a>
    <header className="app-topbar">
      <div className="brand-lockup"><button type="button" className="mobile-menu icon-button" aria-label={menuOpen?"Close navigation":"Open navigation"} aria-expanded={menuOpen} aria-controls="main-navigation" onClick={()=>setMenuOpen(!menuOpen)}><RailIcon name={menuOpen?"close":"menu"}/></button><RMapsMark /><div><strong>R-MAPS</strong><span>Railway Maintenance Allocation &amp; Planning System</span></div></div>
      <div className="topbar-corridor-badge">
        <div className="corridor-text-group">
          <strong>Planning context</strong>
          <small>{selection.snapshotId ? `Snapshot ${selection.snapshotId.slice(0, 8)}` : "Select a saved snapshot"}</small>
        </div>
        <span className="scope-tag">PROTOTYPE</span>
      </div>
      <div className="topbar-tagline">
        <span className="tagline-bullet">●</span>
        <span>Safety · Reliability · Higher Throughput</span>
      </div>
      <div className="topbar-right">
        <span className="prototype-tag">SIH 2026 <span>PROTOTYPE</span></span>
        <span className="user-role-badge">{value?.user.role.replaceAll("_"," ")}</span>
        <details className="account-menu"><summary aria-label="Account and sign out"><span className="avatar">{value?.user.name.slice(0, 1).toUpperCase()}</span></summary><div><strong>{value?.user.name}</strong><span>{value?.user.role}</span><button type="button" className="button button-outline" onClick={()=>void leaveSession()}>Sign out</button>{signOutError&&<p role="alert">{signOutError}</p>}</div></details>
      </div>
    </header>
    <div className="app-body">
      {menuOpen&&<button type="button" className="navigation-scrim" aria-label="Close navigation" onClick={()=>setMenuOpen(false)}/>}
      <aside className="sidebar" id="main-navigation" aria-label="Main navigation" onKeyDown={event=>{if(event.key==="Escape")setMenuOpen(false)}}>
        <nav className="sidebar-nav">{visibleNavigation.map(group=><section className="nav-group" key={group.label} aria-label={group.label}>
          <h2 className="sidebar-heading">{group.label}</h2>
          {group.items.filter(item=>!item.adminOnly||value?.user.role==="ADMIN").map(item=><Link key={item.href} href={item.href} title={item.label} aria-label={item.label} onClick={()=>setMenuOpen(false)} aria-current={pathname===item.href?"page":undefined} className={`nav-item ${pathname===item.href?"nav-item-active":""}`}>
            <RailIcon name={item.icon} size={18}/><span>{item.label}</span>
          </Link>)}
        </section>)}
        </nav>
        <div className="sidebar-bottom"><span className="sidebar-case-label">SAVED PLANNING CONTEXT</span><strong className="mono" title={selection.snapshotId??undefined}>{selection.snapshotId ? selection.snapshotId.slice(0, 8) : "No snapshot selected"}</strong>
          <span>{value?.user.name}</span>
          <button type="button" className="sidebar-signout" onClick={()=>void leaveSession()}>Sign out</button>
          {signOutError && <span role="alert" className="sidebar-error">{signOutError}</span>}
        </div>
      </aside>
      <main className="main-area" id="main-content" tabIndex={-1}>{allowed?children:<section className="panel"><DataState title="Page outside your role workspace" detail="Use your role dashboard to open the maintenance, planning, review or administration tools assigned to you." action="Open your dashboard" onAction={()=>router.push("/dashboard")}/></section>}</main>
    </div>
    <footer className="app-footer"><span>R-MAPS · PS26027</span><span>Decision support prototype · Railway operating authority remains external</span><span>All planning times in IST</span></footer>
  </div>;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const session = useSession();
  const router = useRouter();
  if (session.status === "loading") return <div className="access-state"><RMapsMark /><DataState title="Checking session" detail="Connecting to R-MAPS…" /></div>;
  if (session.status === "offline") return <div className="access-state"><RMapsMark /><DataState title="Backend unavailable" detail="R-MAPS could not read your session. Start or reconnect the API, then retry." action="Retry" onAction={() => void session.refresh()} /></div>;
  if (session.status !== "authenticated" || !session.value) return <div className="access-state"><RMapsMark /><DataState title="Sign in required" detail="Your R-MAPS session is missing or expired." action="Open sign in" onAction={() => router.push("/login")} /></div>;
  return <CaseProvider userId={session.value.user.id}><WorkShell>{children}</WorkShell></CaseProvider>;
}
