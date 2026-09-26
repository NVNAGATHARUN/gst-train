"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { messageFor } from "@/lib/api";
import { useSession } from "@/lib/session";
import { RailIcon } from "@/components/rail-icon";

export default function LoginPage() {
  const { signIn, status, refresh } = useSession();
  const router = useRouter();
  const [credential, setCredential] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const signedIn = await signIn(credential);
      setCredential("");
      router.replace(signedIn.user.role === "PLANNER" ? "/planning" : "/dashboard");
    } catch (cause) {
      setCredential("");
      setError(messageFor(cause));
    } finally { setBusy(false); }
  }
  return <div className="login-page">
    <div className="login-brand"><span className="brand-mark"><RailIcon name="rail" size={26}/></span><strong>RailSync <span className="login-ai">AI</span></strong><span>SIH 2026 <b>PS26027 · PROTOTYPE</b></span></div>
    <div className="login-main">
      <section className="login-form-panel" aria-labelledby="login-title">
        <span className="login-access-icon"><RailIcon name="review" size={24}/></span>
        <span className="eyebrow">YOUR PLANNING DESK</span>
        <h1 id="login-title">Welcome to RailSync</h1>
        <p>Sign in to your department’s maintenance planning workspace.</p>
        {status === "authenticated" ? <div className="inline-note">You already have a session. <a href="/planning">Open Planning Workspace</a></div> : null}
        {status === "offline" ? <div className="inline-alert" role="alert">Backend unavailable. <button type="button" onClick={() => void refresh()}>Retry connection</button></div> : null}
        <form onSubmit={submit} autoComplete="off">
          <label htmlFor="credential">RailSync access credential</label>
          <input id="credential" type="password" name="credential" value={credential} onChange={event => setCredential(event.target.value)} required
            autoComplete="off" aria-describedby="credential-help" />
          <small id="credential-help">Enter the credential assigned by your project administrator. Your role is determined by that credential.</small>
          {error && <div className="inline-alert" role="alert">{error}</div>}
          <button className="button button-primary login-submit" disabled={busy} type="submit">{busy ? "Signing in…" : "Open workspace"}<RailIcon name="arrow" size={18}/></button>
        </form>
        <div className="login-security"><RailIcon name="validate" size={16}/><span>Credentials are not saved in browser storage.</span></div>
      </section>
      <aside className="login-context"><span className="context-kicker">INTEGRATED MAINTENANCE PLANNING</span>
        <h2>Coordinate the work.<br/>Respect the railway.</h2>
        <p className="login-intro">One shared planning state for Engineering, TRD and S&amp;T. Bring maintenance demand, corridor capacity and resources into a proposal your controller can review.</p>
        <div className="login-route-art" aria-hidden="true"><svg viewBox="0 0 540 92" focusable="false">
          <path className="login-route-rail" d="M-15 57 C95 57 115 22 215 30 S365 75 555 30"/>
          <path className="login-route-rail-secondary" d="M-15 71 C95 71 115 36 215 44 S365 89 555 44"/>
          <circle cx="88" cy="42" r="5"/><circle cx="215" cy="30" r="5"/><circle cx="370" cy="55" r="5"/><circle cx="492" cy="45" r="5"/>
        </svg></div>
        <div className="login-departments"><span>Engineering</span><span>TRD / OHE</span><span>S&amp;T</span></div>
        <ol><li><span>01</span><div><strong>Understand the corridor</strong><small>Timetable, COA, freight and restrictions</small></div></li><li><span>02</span><div><strong>Coordinate compatible work</strong><small>Shared capacity, isolation and named resources</small></div></li>
          <li><span>03</span><div><strong>Review an evidenced proposal</strong><small>Independent validation and a human decision</small></div></li></ol>
        <p className="login-authority">Planning decision support. Railway operating authority remains external.</p>
      </aside>
    </div>
    <div className="login-foot"><span>RailSync AI · Integrated block planning</span><span>Engineering · TRD · S&amp;T</span></div>
  </div>;
}
