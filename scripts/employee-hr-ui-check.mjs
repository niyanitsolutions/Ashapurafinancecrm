import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium} from '../frontend/node_modules/.cache/voice-ui-audit/node_modules/playwright/index.mjs';
const origin='http://127.0.0.1:5175';
const actors=JSON.parse(process.env.AFS_TEST_ACTORS||'[]');
const output='docs/screenshots/employee-hr-2026-11-14';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const results=[];
try {for(const width of [1440,390]) {for(const [index,authorization] of actors.entries()) {
 const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});
 await context.addInitScript(()=>localStorage.setItem('afs_refresh_token','isolated-hr-browser'));
 await context.route('**/*',async route=>{
  const req=route.request();const url=new URL(req.url());
  if(!url.pathname.startsWith('/api/v1/'))return url.origin===origin?route.continue():route.abort();
  if(url.pathname==='/api/v1/auth/refresh')return route.fulfill({json:{success:true,data:{access_token:authorization.slice(7),refresh_token:'isolated-hr-browser'},error:null,meta:null}});
  const response=await route.fetch({url:'http://127.0.0.1:18766'+url.pathname+url.search,headers:{...req.headers(),authorization}});
  await route.fulfill({response});
 });
 const page=await context.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
 const paths=index===0?['/profile/onboarding','/profile/leave','/profile/attendance']:['/employees','/employees/onboarding','/employees/attendance','/employees/leave','/employees/edit-requests','/employees/reports','/employees/settings'];
 for(const path of paths){await page.goto(origin+path);await page.waitForLoadState('networkidle');assert.equal(new URL(page.url()).pathname,path,'route must remain accessible');assert.equal(await page.getByText('Unable to load profile.',{exact:true}).count(),0);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${width} ${path} overflow`);await page.screenshot({path:`${output}/${index}-${path.split('/').pop()}-${width}.png`,fullPage:true});}
 assert.deepEqual(errors,[]);results.push({width,role:index===0?'employee':'owner',paths,checks:['actual-api-isolated-mongo','responsive-overflow','no-browser-runtime-errors']});await context.close();
}} await writeFile(output+'/results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));}finally{await browser.close();}
