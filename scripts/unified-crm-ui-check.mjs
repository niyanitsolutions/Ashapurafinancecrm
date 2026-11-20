import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium} from '../frontend/node_modules/.cache/voice-ui-audit/node_modules/playwright/index.mjs';

const origin='http://127.0.0.1:5175';
const fixture=JSON.parse(process.env.AFS_UNIFIED_FIXTURE);
const output='docs/screenshots/unified-crm-2026-11-19';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
let stage='start';
const results=[];
async function connect(context){
 await context.route('**/api/v1/**',async route=>{
  const request=route.request();const url=new URL(request.url());
  const response=await route.fetch({url:'http://127.0.0.1:18772'+url.pathname+url.search});
  await route.fulfill({response});
 });
 await context.route('https://**',route=>route.abort());
}
async function login(page,mobile){
 await page.goto(origin+'/login');await page.getByRole('tab',{name:'Employee / Partner',exact:true}).click();
 await page.locator('#internal-mobile').fill(mobile);await page.locator('#internal-password').fill('InitialPass1!');
 await page.getByRole('button',{name:'Log in',exact:true}).click();await page.waitForURL('**/dashboard');
}
async function capture(page,name,width){
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,`overflow ${name} ${width}`);
 await page.screenshot({path:`${output}/${name}-${width}.png`,fullPage:true});
}
try{
 for(const width of [390,768,1366]){
  stage=`owner-${width}`;const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});await connect(context);
  const page=await context.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.name));
  await login(page,'9000080000');await page.getByRole('heading',{name:'Team operations',exact:true}).waitFor();
  await page.getByText('Lead workload in selected period (1)',{exact:true}).waitFor();await capture(page,'owner-dashboard',width);
  await page.locator('section[aria-label="CRM operations"]').screenshot({path:`${output}/owner-operations-${width}.png`});
  stage=`settings-${width}`;await page.goto(origin+'/settings/auto-assignment');
  await page.getByRole('checkbox',{name:'Team 0 #1',exact:true}).waitFor();await capture(page,'assignment-settings',width);
  if(width===1366){
   await page.getByRole('checkbox',{name:'Enable automatic assignment',exact:true}).uncheck();
   await page.getByRole('button',{name:'Save settings',exact:true}).click();await page.getByText('Assignment settings saved.',{exact:true}).waitFor();
   await page.getByRole('checkbox',{name:'Enable automatic assignment',exact:true}).check();await page.getByRole('button',{name:'Save settings',exact:true}).click();
   await page.getByText('Assignment settings saved.',{exact:true}).waitFor();
  }
  stage=`linked-${width}`;await page.goto(origin+'/leads/'+fixture.lead_id);await page.getByRole('button',{name:'Open Daily Follow-up',exact:true}).click();
  await page.waitForURL(/\/daily-operations\/follow-ups\?record=/);await page.getByRole('heading',{name:'Edit record',exact:true}).waitFor();
  await page.getByRole('link',{name:'Original lead',exact:true}).waitFor();await capture(page,'linked-follow-up',width);
  assert.deepEqual(errors,[]);results.push({width,role:'owner',result:'passed'});await context.unrouteAll({behavior:'ignoreErrors'});await context.close();
 }
 stage='employee';const context=await browser.newContext({viewport:{width:1366,height:1000}});await connect(context);const page=await context.newPage();
 await login(page,'9000080001');await page.getByRole('heading',{name:'My work and priorities',exact:true}).waitFor();
 await page.getByText('Lead workload in selected period (1)',{exact:true}).waitFor();
 assert.equal(await page.getByRole('link',{name:'Auto Assignment Settings',exact:true}).count(),0);
 await capture(page,'employee-dashboard',1366);
 await page.locator('section[aria-label="CRM operations"]').screenshot({path:`${output}/employee-operations-1366.png`});
 await page.goto(origin+'/settings/auto-assignment');await page.waitForURL('**/profile');
 assert.equal(await page.getByRole('heading',{name:'Auto Assignment Settings',exact:true}).count(),0);
 results.push({width:1366,role:'employee',result:'passed'});await context.unrouteAll({behavior:'ignoreErrors'});await context.close();
 await writeFile(output+'/results.json',JSON.stringify({results,backend:'real local FastAPI and disposable MongoDB',external_calls:'none'},null,2));
 console.log(JSON.stringify({results,external_calls:'none'}));
}catch(error){console.error(JSON.stringify({stage,error:error.name,message:String(error.message).slice(0,300)}));process.exitCode=1;}finally{await browser.close();}
