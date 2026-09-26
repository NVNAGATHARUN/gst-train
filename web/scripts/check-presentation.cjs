/* Read-only presentation checks. Archived backend evidence is explicitly SIMULATED.
   No API writes, optimizer substitutes, browser mocks or invented KPI values. */
/* eslint-disable @typescript-eslint/no-require-imports -- Standalone Node CommonJS test loader, not shipped to browsers. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const postcss = require('postcss');
const root = path.resolve(__dirname, '..');
const cache = new Map();
function load(file) {
  let resolved = file;
  if (!path.extname(resolved)) resolved += fs.existsSync(`${file}.tsx`) ? '.tsx' : '.ts';
  if (cache.has(resolved)) return cache.get(resolved).exports;
  const compiledModule = {exports:{}}; cache.set(resolved,compiledModule);
  const compiled = ts.transpileModule(fs.readFileSync(resolved,'utf8'), {compilerOptions:{
    module:ts.ModuleKind.CommonJS, target:ts.ScriptTarget.ES2022, jsx:ts.JsxEmit.ReactJSX,
    esModuleInterop:true,
  }}).outputText;
  const localRequire = name => name.startsWith('@/') ? load(path.join(root,'src',name.slice(2))) :
    name.startsWith('.') ? load(path.resolve(path.dirname(resolved),name)) : require(name);
  new Function('require','module','exports',compiled)(localRequire,compiledModule,compiledModule.exports);
  return compiledModule.exports;
}
const {stackIntervals,timelineTicks} = load(path.join(root,'src/lib/timeline-layout.ts'));
const {timelineItems,intervalStyle} = load(path.join(root,'src/lib/timeline.ts'));
const {TimeTrackTimeline} = load(path.join(root,'src/components/time-track-timeline.tsx'));
const {TaskStages} = load(path.join(root,'src/components/task-stages.tsx'));
const {comparisonMatchesRuns} = load(path.join(root,'src/lib/saved-comparison.ts'));
const source = JSON.parse(fs.readFileSync(path.join(root,'../docs/evidence/M18-workspace-example.json'),'utf8'));
const comparisonSource = JSON.parse(fs.readFileSync(path.join(root,'../docs/evidence/M15-backend-example.json'),'utf8'));
const view = source.workspace;
const output = [];
function check(name,fn){fn();output.push({name,status:'PASS'});console.log(`PASS ${name}`)}
const t = minute => new Date(Date.UTC(2026,8,25,0,minute)).toISOString();
const item = (key,a,b) => ({key,start:t(a),end:t(b)});
const start = Date.parse(t(0)), end = Date.parse(t(120));

check('Half-open touching intervals reuse a visual row',()=>{
  const packed=stackIntervals([item('a',0,30),item('b',30,60)],start,end);
  assert.equal(packed.rows,1);assert.deepEqual(packed.entries.map(x=>x.row),[0,0]);
});
check('Nested and concurrent occupancy remains separately selectable',()=>{
  const packed=stackIntervals([item('a',0,90),item('b',10,20),item('c',15,30)],start,end);
  assert.equal(packed.rows,3);assert.equal(packed.entries.length,3);
});
check('Packing is deterministic for reordered API inputs',()=>{
  const input=[item('z',10,30),item('b',0,20),item('c',20,50)];
  assert.deepEqual(stackIntervals(input,start,end),stackIntervals([...input].reverse(),start,end));
});
check('Invalid, zero-length and out-of-horizon intervals do not create marks',()=>{
  const input=[item('empty',20,20),item('reverse',60,40),item('before',-20,0),item('after',120,130),{key:'bad',start:'unknown',end:t(30)}];
  assert.equal(stackIntervals(input,start,end).entries.length,0);
});
check('Clipping never mutates source intervals',()=>{
  const entry={...item('cross',-20,150),kind:'train',id:'x',track:'AB',label:'SIMULATED',layer:'train'};
  const before=JSON.stringify(entry);
  assert.deepEqual(intervalStyle(entry,start,end),{left:'0%',width:'100%'});
  stackIntervals([entry],start,end);assert.equal(JSON.stringify(entry),before);
});
check('Midnight ticks retain dates and exact horizon endpoints',()=>{
  const a=Date.parse('2026-09-24T18:20:00Z'),b=Date.parse('2026-09-24T18:50:00Z');
  const ticks=timelineTicks(a,b);assert.equal(ticks.length,5);
  assert.equal(Date.parse(ticks[0]),a);assert.equal(Date.parse(ticks[4]),b);
  assert.deepEqual(timelineTicks(b,a),[]);
});
check('Archived backend occupancy and proposal intervals survive projection exactly',()=>{
  assert.equal(view.snapshot.source_scope,'SIMULATED');
  const items=timelineItems(view);
  for(const occupancy of view.facts.occupancy){const match=items.find(x=>x.kind==='train'&&x.id===occupancy.id);assert.ok(match);assert.equal(match.start,occupancy.enter_at);assert.equal(match.end,occupancy.exit_at);}
  const plan=view.selected_revision?.content??view.selected_run?.result;
  assert.equal(items.filter(x=>x.kind==='assignment').length,plan.assignments.reduce((sum,x)=>sum+x.track_ids.length,0));
});
check('Timeline renders actual saved evidence with an exact-time register',()=>{
  const markup=renderToStaticMarkup(React.createElement(TimeTrackTimeline,{view,focus:null,onFocus:()=>{}}));
  assert.ok(markup.includes('SIMULATED'));assert.ok(markup.includes('Interval register'));
  assert.ok(markup.includes('Blank space is not evidence of free capacity.'));
  assert.ok(markup.includes('aria-label="Timeline track"'));
  assert.ok(markup.includes('left:25%'));assert.ok(markup.includes('left:75%'));
});
check('Missing artifacts remain unknown rather than showing computed capacity',()=>{
  const missing={...view,availability:[],coordination:null,selected_run:null,selected_revision:null};
  const markup=renderToStaticMarkup(React.createElement(TimeTrackTimeline,{view:missing,focus:null,onFocus:()=>{}}));
  assert.ok(markup.includes('Capacity not calculated in this context'));
  assert.ok(markup.includes('No plan selected'));
  assert.ok(!markup.includes('timeline-block block-capacity'));
  assert.ok(!markup.includes('timeline-block block-proposal'));
});
check('Invalid saved horizon has a visible error state',()=>{
  const invalid={...view,snapshot:{...view.snapshot,horizon_start:'invalid'}};
  const markup=renderToStaticMarkup(React.createElement(TimeTrackTimeline,{view:invalid,focus:null,onFocus:()=>{}}));
  assert.ok(markup.includes('The saved horizon is invalid'));
});
check('Saved task phases render without recalculate or rounding',()=>{
  const candidate=(view.selected_revision?.content??view.selected_run?.result).assignments[0];
  assert.ok(candidate?.tasks.length);
  const markup=renderToStaticMarkup(React.createElement(TaskStages,{candidate}));
  assert.ok(markup.includes('Restoration'));assert.ok(markup.includes('task-stage-work'));
  assert.equal((markup.match(/class="task-stage-row"/g)??[]).length,candidate.tasks.length);
});
check('Untrusted train labels are escaped by production components',()=>{
  const altered={...view,facts:{...view.facts,occupancy:[{...view.facts.occupancy[0],train_id:'<script>alert(1)</script>'}]}};
  const markup=renderToStaticMarkup(React.createElement(TimeTrackTimeline,{view:altered,focus:null,onFocus:()=>{}}));
  assert.ok(!markup.includes('<script>alert'));assert.ok(markup.includes('&lt;script&gt;'));
});
check('Shared and operational styles parse',()=>{
  for(const file of ['globals.css','workspace.css','operations.css'])postcss.parse(fs.readFileSync(path.join(root,'src/app',file),'utf8'),{from:file});
});
check('Archived comparison matches only its exact snapshot and saved plan pair',()=>{
  const saved=comparisonSource.comparison;
  const content=saved.content;
  const left=[content.baseline.plan_revision_id],right=[content.railsync.plan_revision_id];
  assert.equal(comparisonMatchesRuns(saved,content.snapshot_id,content.snapshot_hash,left,right),true);
  assert.equal(comparisonMatchesRuns(saved,content.snapshot_id,'different-hash',left,right),false);
  assert.equal(comparisonMatchesRuns(saved,content.snapshot_id,content.snapshot_hash,['different-baseline'],right),false);
  assert.equal(comparisonMatchesRuns(saved,content.snapshot_id,content.snapshot_hash,left,['different-optimized']),false);
});
const result={scope:'FRONTEND_PRESENTATION_ONLY',fixture:'archived SIMULATED backend workspace; not current approval evidence',checks:output,passed:output.length,browser_visual_acceptance:'NOT_COVERED'};
fs.writeFileSync(path.join(root,'../docs/evidence/M18-redesign-presentation-checks.json'),JSON.stringify(result,null,2));
console.log(`${output.length} presentation checks passed. Browser visual acceptance remains separate.`);
