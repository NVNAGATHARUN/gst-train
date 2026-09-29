/** Read-only browser review of the running R-MAPS app. No fabricated domain responses. Optional --failure-states aborts domain GETs only.
 * Authentication creates/revokes only this test's browser session. Planning,
 * validation, comparisons and controller writes are blocked by the harness.
 */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright-core';

const webRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const base=new URL(process.env.RAILSYNC_REVIEW_URL??'http://127.0.0.1:3000');
if(!['127.0.0.1','localhost','[::1]'].includes(base.hostname))throw new Error('Review is limited to the local prototype.');
const credential=process.env.RAILSYNC_VISUAL_CREDENTIAL;
const output=path.join(webRoot,'../docs/evidence/browser-review',new Date().toISOString().replaceAll(':','-'));
const routes=['dashboard','planning','corridor','evaluation','validation','review'];
const report={started_at:new Date().toISOString(),scope:'READ_ONLY_CURRENT_BACKEND',screens:[],interactions:[],browser_errors:[],console_errors:[],http_errors:[],expected_navigation_cancellations:[],expected_absences:[],blocked_writes:[],lifecycle:[],visual_acceptance:'PENDING_HUMAN_SCREENSHOT_REVIEW'};
let browser,context,page;
let injectReadFailure=false;
const injectedRequests=new WeakSet();
const safe=message=>credential?String(message).replaceAll(credential,'[REDACTED]'):String(message);
const waitFor=async(predicate,message)=>{
  for(let attempt=0;attempt<180;attempt++){if(await predicate())return;await new Promise(resolve=>setTimeout(resolve,250));}
  throw new Error(message);
};
async function get(endpoint){
  const response=await context.request.get(`${base.origin}/api/v1${endpoint}`);
  if(!response.ok())throw new Error(`Read ${endpoint.split('?')[0]} returned ${response.status()}`);
  return response.json();
}
const fieldSelect=label=>page.locator('.planning-context label.field').filter({hasText:label}).locator('select');
async function select(label,value){
  const control=fieldSelect(label);
  await control.waitFor({timeout:45000});
  await waitFor(async()=>await control.locator('option').evaluateAll((options,id)=>options.some(option=>option.value===id),value),`Option unavailable: ${label}`);
  await control.selectOption(value);
}
async function settled(){
  await page.locator('.main-area .page-heading h1').waitFor();
  if(report.context?.snapshot_id){
    await waitFor(async()=>await fieldSelect('Planning snapshot').inputValue()===report.context.snapshot_id,'Selected planning snapshot did not load');
  }
  await waitFor(async()=>!(await page.locator('.data-state strong').allTextContents()).some(text=>/^(Loading|Checking|Finding saved)/.test(text)),'View remained in a loading state');
  await page.evaluate(()=>document.fonts.ready);
}

try{
  const reachable=await fetch(`${base.origin}/login`,{signal:AbortSignal.timeout(8000)});
  if(!reachable.ok)throw new Error(`Preview returns HTTP ${reachable.status}`);
  if(process.argv.includes('--preflight')){console.log('Local preview reachable. No authentication or browser writes performed.');process.exit(0);}
  if(!credential)throw new Error('Set RAILSYNC_VISUAL_CREDENTIAL to a provisioned prototype credential in your terminal; do not paste it into chat.');
  const executablePath=process.env.RAILSYNC_REVIEW_BROWSER??[
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].find(file=>fs.existsSync(file));
  if(!executablePath)throw new Error('Set RAILSYNC_REVIEW_BROWSER to your installed Chromium browser executable.');
  fs.mkdirSync(output,{recursive:true});
  browser=await chromium.launch({executablePath,headless:true});
  browser.on('disconnected',()=>report.lifecycle.push('Browser disconnected'));
  context=await browser.newContext({viewport:{width:1440,height:1000}});
  context.on('close',()=>report.lifecycle.push('Browser context closed'));
  await context.route('**/api/v1/**',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(!['GET','HEAD','OPTIONS'].includes(request.method())&&url.pathname!=='/api/v1/auth/session'){
      report.blocked_writes.push({method:request.method(),path:url.pathname});
      return route.abort('blockedbyclient');
    }
    if(injectReadFailure&&request.method()==='GET'&&!url.pathname.startsWith('/api/v1/auth/')){
      injectedRequests.add(request);
      report.injected_read_failures.push({path:url.pathname,method:'GET',fault:'connectionfailed'});
      return route.abort('connectionfailed');
    }
    return route.continue();
  });
  page=await context.newPage();
  page.on('close',()=>report.lifecycle.push('Page closed'));
  page.on('requestfailed',request=>{const url=new URL(request.url()),failure=request.failure()?.errorText??'unknown';if(!url.pathname.startsWith('/api/v1/'))return;
    if(injectedRequests.has(request)){report.expected_injected_failures.push({path:url.pathname,error:failure});return;}
    if(request.method()==='GET'&&failure==='net::ERR_ABORTED'){report.expected_navigation_cancellations.push(url.pathname);return;}
    report.browser_errors.push(`API request failed: ${url.pathname} · ${failure}`);
  });
  page.on('pageerror',error=>report.browser_errors.push(safe(error.message)));
  page.on('console',message=>{if(message.type()==='error')report.console_errors.push(safe(message.text()));});
  page.on('response',response=>{const url=new URL(response.url());if(!url.pathname.startsWith('/api/v1/')||response.status()<400)return;
    if(url.pathname==='/api/v1/auth/session'&&response.status()===401)return;
    if(response.status()===404&&/^\/api\/v1\/plan-revisions\/[^/]+\/differences$/.test(url.pathname)){
      report.expected_absences.push({path:url.pathname,status:404,meaning:'No saved difference artifact for this revision'});return;
    }
    report.http_errors.push({path:url.pathname,status:response.status()});
  });
  await page.goto(`${base.origin}/login`);
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:width===390?844:1000});
    await page.evaluate(()=>document.fonts.ready);
    const filename=`login-${width}.png`;
    await page.screenshot({path:path.join(output,filename),fullPage:true,caret:'initial'});
    const metrics=await page.evaluate(()=>({viewport:document.documentElement.clientWidth,document:document.documentElement.scrollWidth}));
    report.screens.push({route:'login',width,file:filename,horizontal_page_overflow:metrics.document>metrics.viewport+1,states:[],alerts:[]});
  }
  report.login_dev_indicator=await page.evaluate(()=>Array.from(document.querySelectorAll('nextjs-portal')).flatMap(portal=>
    Array.from(portal.shadowRoot?.querySelectorAll('button')??[]).map(button=>button.getAttribute('aria-label')??button.textContent?.trim()??'').filter(Boolean)).slice(0,12));
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('#credential').fill(credential);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/planning');
  await page.getByRole('heading',{name:'Planning workspace',exact:true}).waitFor({timeout:45000});
  await page.screenshot({path:path.join(output,'initial-planning.png'),fullPage:true,caret:'initial'});
  const snapshots=await get('/workspace/snapshots?scenario=ANY&limit=100');
  let selected,runs;
  for(const snapshot of snapshots.items){
    const candidateRuns=await get(`/workspace/runs?snapshot_id=${encodeURIComponent(snapshot.id)}&limit=100`);
    if(candidateRuns.items.some(run=>run.planner_type==='CP_SAT'&&run.revision_ids.length)){
      selected=snapshot;runs=candidateRuns.items;break;
    }
  }
  if(!selected)throw new Error('No saved CP-SAT proposal exists for a meaningful hero review. No new results were generated.');
  const chosenRun=runs.find(run=>run.planner_type==='CP_SAT'&&run.revision_ids.length);
  const baselineRun=runs.find(run=>run.planner_type==='BASELINE'&&run.revision_ids.length);
  const sessions=await get(`/workspace/planning-sessions?snapshot_id=${encodeURIComponent(selected.id)}&limit=100`);
  const chosenSession=sessions.items.find(session=>session.runs.some(run=>run.id===chosenRun.id));
  report.context={snapshot_id:selected.id,source_scope:selected.source_scope,revision_id:chosenRun.revision_ids[0],session_id:chosenSession?.id??null};
  await select('Planning snapshot',selected.id);
  if(chosenSession)await select('Planning session',chosenSession.id);
  await select('Plan evidence',`revision:${chosenRun.revision_ids[0]}`);
  await page.getByRole('heading',{name:'Corridor planning diagram',exact:true}).waitFor();
  const readStatusPairs=()=>page.locator('.session-metrics > div').evaluateAll(rows=>Object.fromEntries(rows.map(row=>[
    row.querySelector('span')?.textContent?.trim()??'',row.querySelector('strong')?.textContent?.trim()??'',
  ])));
  await waitFor(async()=>{const pairs=await readStatusPairs();return !['Not run','No saved run',undefined].includes(pairs['CP-SAT'])&&
    (!baselineRun||!['Not run','No saved run',undefined].includes(pairs.Baseline));},'Planning panel did not show saved CP-SAT/baseline run statuses');
  const statusPairs=await readStatusPairs();
  report.planning_status_evidence={preparation:statusPairs.Preparation,baseline:statusPairs.Baseline,cp_sat:statusPairs['CP-SAT']};
  // Exercise view-only interactions against the actual recorded intervals.
  const diagram=page.locator('.timeline-panel').first();
  await diagram.getByRole('button',{name:'2×',exact:true}).click();
  if(await diagram.locator('.timeline-inner').evaluate(node=>node.style.width)!=='200%')throw new Error('Timeline zoom did not change the visible scale.');
  await diagram.getByRole('button',{name:'Fit',exact:true}).click();
  report.interactions.push('Planning timeline scale changed to 2× and back to Fit');
  const firstInterval=diagram.locator('.timeline-block').first();
  if(await firstInterval.count()){
    await firstInterval.click();
    await page.getByRole('heading',{name:'Evidence inspector',exact:true}).waitFor();
    report.interactions.push('Selecting an actual interval opens the evidence inspector');
  }
  for(const width of [1440,1920,390]){
    await page.setViewportSize({width,height:width===390?844:1080});
    for(const route of routes){
      await page.goto(`${base.origin}/${route}`);
      await settled();
      if(route==='evaluation'&&!chosenSession&&baselineRun){
        await select('First-feasible run',baselineRun.id);
        await select('R-MAPS CP-SAT run',chosenRun.id);
        await settled();
      }
      const filename=`${route}-${width}.png`;
      await page.screenshot({path:path.join(output,filename),fullPage:true,caret:'initial'});
      const metrics=await page.evaluate(()=>({viewport:document.documentElement.clientWidth,document:document.documentElement.scrollWidth}));
      report.screens.push({route,width,file:filename,horizontal_page_overflow:metrics.document>metrics.viewport+1,states:await page.locator('.data-state strong').allTextContents(),alerts:await page.locator('main [role="alert"]').allTextContents()});
      if(route==='evaluation'&&width===1440){
        report.comparison_coverage=await page.locator('.comparison-highlights').count()?'SAVED_METRICS_VISIBLE':'NO_SAVED_METRICS_IN_SELECTED_CONTEXT';
      }
      if(width===390){
        await page.getByRole('button',{name:'Open navigation',exact:true}).click();
        if(!(await page.getByRole('link',{name:'Block planning',exact:true}).isVisible()))throw new Error('Mobile navigation did not expose planning.');
        await page.getByRole('button',{name:'Close navigation',exact:true}).first().click();
      }
    }
  }
  if(process.argv.includes('--accessibility')){
    report.accessibility_scope='Focused keyboard controls and 720 CSS-pixel viewport reflow (1440 / 2); native browser zoom and full accessibility audit remain manual gates';
    await page.setViewportSize({width:1440,height:1080});
    await page.goto(`${base.origin}/planning`);
    await settled();
    const skip=page.locator('.skip-link');
    await skip.focus();
    await page.keyboard.press('Enter');
    if(!await page.locator('#main-content').evaluate(node=>node===document.activeElement))throw new Error('Skip link did not focus the workspace');
    report.interactions.push('Keyboard: skip link focuses main workspace');
    const timeline=page.locator('.timeline-panel').first();
    const zoom=timeline.getByRole('button',{name:'2×',exact:true});
    await zoom.focus();await page.keyboard.press('Enter');
    if(await zoom.getAttribute('aria-pressed')!=='true')throw new Error('Keyboard timeline zoom did not expose selected state');
    await timeline.getByRole('button',{name:'Fit',exact:true}).focus();await page.keyboard.press('Enter');
    const interval=timeline.locator('.timeline-block').first();
    if(await interval.count()){
      await interval.focus();await page.keyboard.press('Enter');
      await page.getByRole('heading',{name:'Evidence inspector',exact:true}).waitFor();
      if(await interval.getAttribute('aria-pressed')!=='true')throw new Error('Keyboard interval selection did not expose selected state');
      report.interactions.push('Keyboard: actual interval selection opens its evidence inspector');
    }
    report.interactions.push('Keyboard: timeline scale responds to Enter and exposes pressed state');
    for(const route of routes.filter(route=>route!=='dashboard')){
      await page.goto(`${base.origin}/${route}`);await settled();
      if(route==='evaluation'&&!chosenSession&&baselineRun){
        await select('First-feasible run',baselineRun.id);await select('R-MAPS CP-SAT run',chosenRun.id);await settled();
      }
      await page.setViewportSize({width:720,height:540});
      const filename=`${route}-reflow-720.png`;
      await page.screenshot({path:path.join(output,filename),fullPage:true,caret:'initial'});
      const metrics=await page.evaluate(()=>({viewport:document.documentElement.clientWidth,document:document.documentElement.scrollWidth}));
      report.screens.push({route,width:720,reflow_reference:{physical_width:1440,zoom_factor:2,method:"viewport-width proxy; not native browser zoom"},file:filename,horizontal_page_overflow:metrics.document>metrics.viewport+1,states:await page.locator('.data-state strong').allTextContents(),alerts:await page.locator('main [role="alert"]').allTextContents()});
      await page.setViewportSize({width:1440,height:1080});
    }
  }
  if(process.argv.includes('--failure-states')){
    report.failure_state_scope='TEST FAULT INJECTION: fresh-page domain GET connection failures; auth remains real; recovery uses actual backend; no decisions submitted';
    report.injected_read_failures=[];report.expected_injected_failures=[];report.failure_states=[];
    await page.setViewportSize({width:1440,height:1080});
    for(const route of routes.filter(route=>route!=='dashboard')){
      injectReadFailure=true;
      try{
        await page.goto(`${base.origin}/${route}`);
        await page.locator('.main-area .page-heading h1').waitFor();
        await page.locator('main [role="alert"]').first().waitFor({timeout:15000});
        await waitFor(async()=>!(await page.locator('.data-state strong').allTextContents()).some(text=>/^(Loading|Checking|Finding saved)/.test(text)),`${route} remained loading after a failed API read`);
        const alerts=await page.locator('main [role="alert"]').allTextContents();
        if(!alerts.some(text=>/API|backend|connection|retry|reach/i.test(text)))throw new Error(`${route} did not explain the failed backend read`);
        if(await page.locator('.timeline-block,.comparison-highlights').count())throw new Error(`${route} displayed operational results with fresh-page reads unavailable`);
        const submit=page.getByRole('button',{name:'Record proposal approval',exact:true});
        if(await submit.count()&&!await submit.isDisabled())throw new Error('Controller approval remained enabled without backend evidence');
        const filename=`${route}-api-unavailable.png`;
        await page.screenshot({path:path.join(output,filename),fullPage:true,caret:'initial'});
        report.failure_states.push({route,fault:'domain GET connection failure',alerts,states:await page.locator('.data-state strong').allTextContents(),file:filename,operational_results_absent:true,approval_absent_or_disabled:true,recovered:false});
      }finally{injectReadFailure=false;}
      await page.goto(`${base.origin}/${route}`);await settled();
      if(route==='evaluation'&&!chosenSession&&baselineRun){
        await select('First-feasible run',baselineRun.id);await select('R-MAPS CP-SAT run',chosenRun.id);await settled();
      }
      if(await page.locator('main [role="alert"]').count())throw new Error(`${route} retained an API error after restoring backend access`);
      if(!await page.locator('.timeline-panel').count())throw new Error(`${route} did not restore saved timeline evidence`);
      if(route==='evaluation'&&!await page.locator('.comparison-highlights').count())throw new Error('Saved comparison did not recover');
      const filename=`${route}-api-recovered.png`;
      await page.screenshot({path:path.join(output,filename),fullPage:true,caret:'initial'});
      Object.assign(report.failure_states.at(-1),{recovered:true,recovery_file:filename});
    }
    if(!report.injected_read_failures.length||report.failure_states.length!==5)throw new Error('Fault-injection coverage incomplete');
  }
  report.completed_at=new Date().toISOString();
  report.status=report.browser_errors.length||report.console_errors.some(error=>!error.startsWith('Failed to load resource:'))||report.http_errors.length||report.blocked_writes.length||report.screens.some(screen=>screen.horizontal_page_overflow)?'REVIEW_ISSUES_FOUND':
    report.comparison_coverage!=='SAVED_METRICS_VISIBLE'?'INCOMPLETE_EVIDENCE':'CAPTURED_REQUIRES_VISUAL_REVIEW';
  if(report.status!=='CAPTURED_REQUIRES_VISUAL_REVIEW')process.exitCode=1;
  console.log(`${report.screens.length} real-backend screenshots captured. Inspect images before accepting the design.`);
}catch(error){
  report.status='BLOCKED';report.error=safe(error.message);
  if(error.cause?.code)report.connection_error=error.cause.code;
  if(page){
    try{report.failure_context={url:page.url(),headings:await page.getByRole('heading').allTextContents(),
      alerts:await page.locator('[role="alert"]').allTextContents(),
      data_states:await page.locator('.data-state strong').allTextContents(),
      snapshot_options:await fieldSelect('Planning snapshot').locator('option').allTextContents()};
      await page.screenshot({path:path.join(output,'failure.png'),fullPage:true,caret:'initial'});
    }catch(diagnosticError){report.failure_diagnostic_error=safe(diagnosticError.message)}
  }
  console.error(`${safe(error.message)}${error.cause?.code?` (${error.cause.code})`:''}`);process.exitCode=1;
}
finally{
  if(context){
    try{const session=await get('/auth/session');await context.request.delete(`${base.origin}/api/v1/auth/session`,{headers:{'X-CSRF-Token':session.csrf_token,Origin:base.origin}});}catch{report.session_cleanup='Could not confirm session revocation; browser context closed.';}
  }
  await browser?.close();
  if(fs.existsSync(output)){fs.writeFileSync(path.join(output,'review.json'),JSON.stringify(report,null,2));console.log(`Review evidence: ${output}`);}
}
