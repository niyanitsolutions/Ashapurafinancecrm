import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium} from '../frontend/node_modules/.cache/voice-ui-audit/node_modules/playwright/index.mjs';
const origin='http://127.0.0.1:5175';
const fixture=JSON.parse(process.env.AFS_ASSIGNMENT_FIXTURE);
const output='docs/screenshots/assignment-enhancement-2026-11-20';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const results=[];let stage='start';let activePage=null;const apiFailures=[];
async function capture(page,name,width){
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
 await page.screenshot({path:`${output}/${name}-${width}.png`,fullPage:true});
}
try{
 for(const [index,width] of [390,768,1366].entries()){
  const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});
  await context.route('**/api/v1/**',async route=>{const url=new URL(route.request().url());const response=await route.fetch({url:'http://127.0.0.1:18773'+url.pathname+url.search});await route.fulfill({response});});
  await context.route('https://**',route=>route.abort());
  const page=await context.newPage();activePage=page;const errors=[];page.on('pageerror',error=>errors.push(error.name));
  page.on('response',response=>{if(response.status()>=400 && response.url().includes('/api/v1/'))apiFailures.push({path:new URL(response.url()).pathname,status:response.status()});});
  stage=`login-${width}`;await page.goto(origin+'/login');await page.getByRole('tab',{name:'Employee / Partner',exact:true}).click();
  await page.locator('#internal-mobile').fill('9000080000');await page.locator('#internal-password').fill('InitialPass1!');await page.getByRole('button',{name:'Log in',exact:true}).click();await page.waitForURL('**/dashboard');
  const employee=fixture.employees[(index+1)%fixture.employees.length];
  for(const [path,noun] of [['/leads','Leads'],['/leads/document-collection','Applications']]){
   stage=`${noun}-${width}`;await page.goto(origin+path);await page.getByRole('checkbox',{name:'Select all',exact:true}).waitFor();
   if(noun==='Applications')await page.getByText('Actual Applicant',{exact:true}).waitFor();
   await page.getByRole('checkbox',{name:'Select all',exact:true}).check();await page.getByText(`1 ${noun} Selected`,{exact:true}).waitFor();
   await page.getByRole('button',{name:'Assign Selected',exact:true}).click();
   await page.getByLabel('Select Employee',{exact:true}).selectOption(employee);
   await page.getByRole('checkbox',{name:'I explicitly authorize replacing existing assignments on the selected records.',exact:true}).check();
   await page.getByRole('button',{name:'Review assignments',exact:true}).click();await page.getByRole('button',{name:`Assign 1 ${noun}`,exact:true}).waitFor();
   await capture(page,`${noun.toLowerCase()}-preview`,width);
   await page.getByRole('button',{name:`Assign 1 ${noun}`,exact:true}).click();await page.getByText('Successfully assigned: 1 · Skipped: 0 · Failed: 0',{exact:true}).waitFor();
   assert.equal(await page.getByText(`1 ${noun} Selected`,{exact:true}).count(),0);
   await capture(page,`${noun.toLowerCase()}-assigned`,width);
  }
  assert.deepEqual(errors,[]);results.push({width,result:'passed',journeys:['Fresh bulk preview/confirm','Document Collection actual seeded applicant name','Application bulk preview/confirm','selection cleared']});
  await context.unrouteAll({behavior:'ignoreErrors'});await context.close();
 }
 await writeFile(output+'/results.json',JSON.stringify({results,backend:'real local FastAPI and disposable MongoDB',external_calls:'none'},null,2));console.log(JSON.stringify({results,external_calls:'none'}));
}catch(error){if(activePage)await activePage.screenshot({path:output+'/failure.png',fullPage:true}).catch(()=>{});console.error(JSON.stringify({stage,error:error.name,message:String(error.message).slice(0,250),apiFailures}));process.exitCode=1;}finally{await browser.close();}
