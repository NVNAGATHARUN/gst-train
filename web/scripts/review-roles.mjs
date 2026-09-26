/** Read-only role review for the explicitly isolated local lifecycle demo. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright-core';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const base='http://127.0.0.1:3001';
if(!process.argv.includes('--isolated-demo'))throw new Error('Requires --isolated-demo; fixed fixture credentials must never be used against another environment.');
const output=path.join(root,'../docs/evidence/role-review',new Date().toISOString().replaceAll(':','-'));
fs.mkdirSync(output,{recursive:true});
const cases=[
  {credential:'ENGINEERING',role:'DEPARTMENT',title:'Department Maintenance Desk',count:3,denied:'/review',primary:'/maintenance'},
  {credential:'PLANNER',role:'PLANNER',title:'Planning Dashboard',count:12,denied:'/system',primary:'/planning'},
  {credential:'CONTROLLER',role:'CONTROLLER',title:'Controller Dashboard',count:11,denied:'/optimization',primary:'/review'},
  {credential:'AUDITOR',role:'AUDITOR',title:'Audit Dashboard',count:11,denied:'/changes',primary:'/reports'},
  {credential:'ADMIN',role:'ADMIN',title:'Administration Dashboard',count:5,denied:'/optimization',primary:'/system'},
];
const report={scope:'READ_ONLY_ISOLATED_SIMULATED_ROLE_REVIEW',started_at:new Date().toISOString(),roles:[],errors:[],blocked_writes:[],visual_acceptance:'PENDING_SCREENSHOT_INSPECTION'};
let browser;
try{
 const executablePath=process.env.RAILSYNC_REVIEW_BROWSER??['C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(fs.existsSync);
 if(!executablePath)throw new Error('Installed Chromium browser not found.');
 browser=await chromium.launch({executablePath,headless:true});
 for(const fixture of cases){
  const context=await browser.newContext({viewport:{width:1440,height:1080}});
  const page=await context.newPage();
  page.on('pageerror',error=>report.errors.push({role:fixture.role,message:error.message}));
  await context.route('**/api/v1/**',async route=>{
   const request=route.request(),url=new URL(request.url());
   if(!['GET','HEAD','OPTIONS'].includes(request.method())&&url.pathname!=='/api/v1/auth/session'){
    report.blocked_writes.push({role:fixture.role,path:url.pathname});return route.abort('blockedbyclient');
   }
   return route.continue();
  });
  try{
   await page.goto(base+'/login');
   await page.locator('#credential').fill(fixture.credential);
   await page.locator('button[type="submit"]').click();
   await page.waitForURL(fixture.role==='PLANNER'?'**/planning':'**/dashboard',{timeout:15000});
   const sessionResponse=await context.request.get(base+'/api/v1/auth/session');
   if(!sessionResponse.ok())throw new Error(`${fixture.role}: session unavailable`);
   const session=await sessionResponse.json();
   if(session.user.role!==fixture.role)throw new Error('Authenticated role mismatch');
   await page.goto(base+'/dashboard');
   await page.getByRole('heading',{name:fixture.title,exact:true}).waitFor();
   await page.waitForFunction(()=>!Array.from(document.querySelectorAll('.data-state strong')).some(node=>node.textContent?.startsWith('Loading')));
   if(await page.locator('main [role="alert"]').count())throw new Error(`${fixture.role}: dashboard API error`);
   const links=await page.locator('.sidebar-nav a').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('href')));
   if(links.length!==fixture.count||!links.includes(fixture.primary))throw new Error(`${fixture.role}: unexpected navigation`);
   const evidence={role:fixture.role,department:session.user.department,links,screens:[],denied_route:fixture.denied};
   if(['PLANNER','CONTROLLER','AUDITOR'].includes(fixture.role)){
    const snapshotsResponse=await context.request.get(base+'/api/v1/workspace/snapshots?scenario=ANY&limit=100');
    if(!snapshotsResponse.ok())throw new Error('Saved snapshots unavailable');
    const snapshots=await snapshotsResponse.json();let selected;
    for(const snapshot of snapshots.items.filter(item=>item.source_scope==='SIMULATED')){
     const response=await context.request.get(base+`/api/v1/workspace/runs?snapshot_id=${snapshot.id}&limit=100`);
     if(!response.ok())throw new Error('Saved runs unavailable');
     const runs=await response.json();const run=runs.items.find(item=>item.planner_type==='CP_SAT'&&item.revision_ids.length);
     if(run){selected={snapshot:snapshot.id,revision:run.revision_ids[0]};break;}
    }
    if(!selected)throw new Error('No saved simulated CP-SAT proposal for populated dashboard review');
    const field=name=>page.locator('.planning-context label.field').filter({hasText:name}).locator('select');
    await field('Planning snapshot').selectOption(selected.snapshot);
    await page.waitForFunction(id=>Array.from(document.querySelectorAll('.planning-context select option')).some(option=>option.value===id),selected.revision);
    await field('Proposal revision').selectOption(selected.revision);
    await page.locator('.dashboard-state-banner').waitFor();
    await page.waitForFunction(()=>!Array.from(document.querySelectorAll('.dashboard-state-banner')).some(node=>node.textContent?.includes('Reading decision history')));
    if(await page.locator('main [role="alert"]').count())throw new Error('Populated dashboard API error');
    evidence.selected_snapshot=selected.snapshot;evidence.selected_revision=selected.revision;evidence.populated_case=true;
   }

   for(const width of [1440,390]){
    await page.setViewportSize({width,height:width===390?844:1080});
    await page.evaluate(()=>document.fonts.ready);
    const file=`${fixture.role.toLowerCase()}-${width}.png`;
    await page.screenshot({path:path.join(output,file),fullPage:true,caret:'initial'});
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth+1);
    if(overflow)throw new Error(`${fixture.role}: page overflow at ${width}`);
    if(width===390){
     await page.getByRole('button',{name:'Open navigation',exact:true}).click();
     if(!await page.locator(`.sidebar-nav a[href="${fixture.primary}"]`).isVisible())throw new Error('Mobile primary action missing');
     await page.getByRole('button',{name:'Close navigation',exact:true}).first().click();
    }
    evidence.screens.push({file,width,horizontal_page_overflow:false});
   }
   await page.goto(base+fixture.denied);
   await page.getByText('Page outside your role workspace',{exact:true}).waitFor();
   evidence.direct_route_denied=true;
   report.roles.push(evidence);
  }finally{
   try{
    const response=await context.request.get(base+'/api/v1/auth/session');
    if(response.ok()){const session=await response.json();const revoked=await context.request.delete(base+'/api/v1/auth/session',{headers:{'X-CSRF-Token':session.csrf_token,Origin:base}});if(!revoked.ok())report.errors.push({role:fixture.role,message:'Session cleanup failed'});}
   }finally{await context.close();}
  }
 }
 report.status=report.errors.length||report.blocked_writes.length?'REVIEW_ISSUES_FOUND':'CAPTURED_REQUIRES_VISUAL_REVIEW';
 if(report.status==='REVIEW_ISSUES_FOUND')process.exitCode=1;
 console.log(`${report.roles.length} role dashboards checked; inspect the 10 captured views before accepting visual quality.`);
}catch(error){report.status='BLOCKED';report.error=error.message;console.error(error.message);process.exitCode=1;}
finally{await browser?.close();report.completed_at=new Date().toISOString();fs.writeFileSync(path.join(output,'review.json'),JSON.stringify(report,null,2));console.log('Review evidence: '+output);}
