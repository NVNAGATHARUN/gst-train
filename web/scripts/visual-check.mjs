import { chromium } from "playwright-core";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const output = process.env.RAILSYNC_VISUAL_OUTPUT || path.resolve("..", ".local", "m18-visual");
const credential = process.env.RAILSYNC_VISUAL_CREDENTIAL;
if (!credential) throw new Error("Set RAILSYNC_VISUAL_CREDENTIAL to a fixture-only credential.");
await mkdir(output, {recursive:true});
const browser = await chromium.launch({executablePath:"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", headless:true, args:["--no-sandbox"]});
const page = await browser.newPage({viewport:{width:1440,height:900},deviceScaleFactor:1});
const errors=[];
page.on("pageerror", error=>errors.push(error.message));
try {
  await page.goto("http://127.0.0.1:3000/login",{waitUntil:"networkidle"});
  await page.getByLabel("Provisioned RailSync credential").fill(credential);
  await page.getByRole("button",{name:"Sign in"}).click();
  await page.getByRole("heading",{name:"Planning workspace"}).waitFor();
  const snapshot = page.getByLabel("Planning snapshot");
  await snapshot.locator("option").nth(1).waitFor();
  await snapshot.selectOption({index:1});
  await page.getByText("Maintenance demand",{exact:true}).waitFor();
  const planOptions=await page.getByLabel("Plan evidence").locator("option").allTextContents();
  const revisionIndex=planOptions.findIndex(x=>x.startsWith("Saved proposal"));
  if (revisionIndex>=0) await page.getByLabel("Plan evidence").selectOption({index:revisionIndex});
  const demand=page.locator(".demand-card").first();
  if (await demand.count()) await demand.click();
  await page.screenshot({path:path.join(output,"planning-1440.png"),fullPage:true});
  await page.setViewportSize({width:1920,height:1080});
  await page.screenshot({path:path.join(output,"planning-1920.png"),fullPage:true});
  await page.getByRole("link",{name:/Maintenance/}).click();
  await page.getByRole("heading",{name:"Maintenance requirements"}).waitFor();
  await page.screenshot({path:path.join(output,"maintenance-1440.png"),fullPage:true});
  console.log(JSON.stringify({output,planOptions,revisionIndex,errors,maintenanceRows:await page.locator(".maintenance-table tbody tr").count()}));
  if(errors.length)process.exitCode=1;
} finally {await browser.close();}
