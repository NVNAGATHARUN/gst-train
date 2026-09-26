/** UI workflow boundaries; backend authorization remains authoritative. */
const pages: Record<string, readonly string[]> = {
  DEPARTMENT: ['/dashboard','/maintenance','/data-readiness'],
  PLANNER: ['/dashboard','/maintenance','/planning','/corridor','/optimization','/evaluation','/validation','/review','/schedules','/changes','/reports','/data-readiness'],
  CONTROLLER: ['/dashboard','/maintenance','/planning','/corridor','/validation','/review','/schedules','/changes','/execution','/reports','/data-readiness'],
  AUDITOR: ['/dashboard','/maintenance','/planning','/corridor','/evaluation','/validation','/review','/schedules','/execution','/reports','/data-readiness'],
  ADMIN: ['/dashboard','/data-readiness','/admin','/system','/reports'],
};
export function canOpenPage(role: string | undefined, path: string): boolean {
  return !!role && !!pages[role]?.includes(path);
}
export const roleDashboard: Record<string,{title:string;detail:string;href:string;action:string}> = {
  DEPARTMENT:{title:'Department Maintenance Desk',detail:'Raise and track your department’s requirements, prerequisites and source imports.',href:'/maintenance',action:'Open Maintenance Demand'},
  PLANNER:{title:'Planning Dashboard',detail:'Coordinate maintenance demand with corridor capacity and compare feasible block proposals.',href:'/planning',action:'Open Planning Workspace'},
  CONTROLLER:{title:'Controller Dashboard',detail:'Review current proposal evidence, record decisions and track execution and handback.',href:'/review',action:'Open Controller Review'},
  AUDITOR:{title:'Audit Dashboard',detail:'Inspect saved planning facts, validation, decisions and observed execution evidence.',href:'/reports',action:'Open Reports & Audit'},
  ADMIN:{title:'Administration Dashboard',detail:'Maintain network and rules, inspect source readiness and monitor service health.',href:'/system',action:'Open System Health'},
};
