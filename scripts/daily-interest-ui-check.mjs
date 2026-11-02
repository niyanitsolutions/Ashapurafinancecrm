// Actual local API and isolated real MongoDB. Authentication uses API-test sessions.
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium} from '../frontend/node_modules/.cache/voice-ui-audit/node_modules/playwright/index.mjs';
const origin='http://127.0.0.1:5175';
const actors=JSON.parse(process.env.AFS_TEST_ACTORS||'[]');assert.equal(actors.length,2);
const output='docs/screenshots/daily-interest-2026-11-02';await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const results=[];
try{
 for(const width of [1440,390]){
  const contexts=[];const pages=[];const errors=[];
  for(const authorization of actors){
   const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});contexts.push(context);
   await context.addInitScript(()=>localStorage.setItem('afs_refresh_token','isolated-browser-session'));
   await context.route('**/*',async route=>{
    const req=route.request();const url=new URL(req.url());
    if(!url.pathname.startsWith('/api/v1/'))return url.origin===origin?route.continue():route.abort();
    if(url.pathname==='/api/v1/auth/refresh')return route.fulfill({json:{success:true,data:{access_token:authorization.slice(7),refresh_token:'isolated-browser-session'},error:null,meta:null}});
    const response=await route.fetch({url:'http://127.0.0.1:18765'+url.pathname+url.search,headers:{...req.headers(),authorization}});
    if(response.status()>=400)console.log(url.pathname,response.status(),(await response.text()).slice(0,300));
    await route.fulfill({response});
   });
   const page=await context.newPage();pages.push(page);page.on('pageerror',e=>errors.push(e.message));
   await page.goto(origin+'/daily-operations/follow-ups');await page.getByRole('heading',{name:'Daily Follow-up Data',exact:true}).waitFor({timeout:15000}).catch(async e=>{console.log('Browser state',page.url(),await page.locator('body').innerText(),errors);throw e;});
  }
  const [a,b]=pages;
  async function add(page){await page.getByRole('button',{name:'+ Add record',exact:true}).click();return page.getByRole('dialog');}
  async function open(dialog){await dialog.getByLabel('Customer Interest Status',{exact:true}).click();await dialog.getByLabel('Available interest options',{exact:true}).waitFor();}
  async function custom(dialog,name){await dialog.getByRole('button',{name:'Add Custom Option',exact:true}).click();await dialog.getByLabel('Option name',{exact:true}).fill(name);await dialog.getByRole('button',{name:'Save option',exact:true}).click();await dialog.getByText('Option saved.',{exact:true}).waitFor();}
  let da=await add(a);await open(da);await custom(da,'Browser interest A');
  await da.getByLabel('Customer name',{exact:true}).fill('Browser Customer '+width);await da.getByLabel('Customer number',{exact:true}).fill('9000000000');await da.getByLabel('Bank / NBFC',{exact:true}).fill('Browser Bank');
  await da.getByRole('button',{name:'Save record',exact:true}).click();await da.waitFor({state:'hidden'});
  const row=a.getByRole('row').filter({hasText:'Browser Customer '+width});await row.waitFor();
  let db=await add(b);await open(db);await db.getByRole('option',{name:'Browser interest A',exact:true}).waitFor();
  await custom(db,'Browser interest B '+width);
  da=await add(a);await open(da);await da.getByRole('option',{name:'Browser interest B '+width,exact:true}).waitFor();await da.getByRole('button',{name:'Cancel',exact:true}).click();
  await row.getByRole('button',{name:'Edit',exact:true}).click();da=a.getByRole('dialog');assert.match(await da.getByLabel('Customer Interest Status',{exact:true}).innerText(),/Browser interest A/);
  await db.getByRole('button',{name:'Manage Options',exact:true}).click();await db.getByRole('button',{name:'Edit Browser interest A',exact:true}).click();await db.getByLabel('Option name',{exact:true}).fill('Browser updated A '+width);await db.getByRole('button',{name:'Save option',exact:true}).click();
  await db.getByRole('button',{name:'Remove Browser updated A '+width,exact:true}).click();await b.getByRole('button',{name:'Remove option',exact:true}).click();await db.getByRole('button',{name:'Restore Browser updated A '+width,exact:true}).waitFor();
  await open(da);await da.getByRole('button',{name:'Refresh options',exact:true}).click();await da.getByRole('option',{name:/Browser interest A.*archived/}).waitFor();
  await da.getByLabel("Today's case status / remarks",{exact:true}).fill('Edited after archive');await a.screenshot({path:`${output}/employee-${width}.png`,fullPage:true});
  await da.getByRole('button',{name:'Save changes',exact:true}).click();await da.waitFor({state:'hidden'});await row.getByText('Browser interest A',{exact:true}).waitFor();await row.getByText('Edited after archive',{exact:true}).waitFor();
  da=await add(a);await open(da);assert.equal(await da.getByRole('option',{name:/Browser interest A/}).count(),0);await da.getByRole('button',{name:'Cancel',exact:true}).click();
  assert.deepEqual(errors,[]);results.push({width,result:'passed',backend:'actual FastAPI',database:'isolated local MongoDB',checks:['two-employee-sharing','create-and-autoselect','save-record','cross-session-refresh','edit-retention','rename','archive-confirmation','historical-label-preserved','archived-new-selection-excluded']});
  for(const context of contexts)await context.close();
 }
 await writeFile(output+'/results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close();}
