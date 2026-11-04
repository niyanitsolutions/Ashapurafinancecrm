// Actual local API + isolated MongoDB; test sessions for two authorized employees.
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium} from '../frontend/node_modules/.cache/voice-ui-audit/node_modules/playwright/index.mjs';
const origin='http://127.0.0.1:5175';const actors=JSON.parse(process.env.AFS_TEST_ACTORS||'[]');assert.equal(actors.length,2);
const output='docs/screenshots/daily-followup-status-2026-11-04';await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});const results=[];
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
    const response=await route.fetch({url:'http://127.0.0.1:18765'+url.pathname+url.search,headers:{...req.headers(),authorization}});await route.fulfill({response});
   });
   const page=await context.newPage();pages.push(page);page.on('pageerror',e=>errors.push(e.message));
   await page.goto(origin+'/daily-operations/follow-ups');await page.getByRole('heading',{name:'Daily Follow-up Data',exact:true}).waitFor();
   assert.equal(await page.getByText('CUSTOMER INTEREST STATUS',{exact:true}).count(),0);
  }
  const [a,b]=pages;
  async function add(page){await page.getByRole('button',{name:'+ Add record',exact:true}).click();return page.getByRole('dialog');}
  async function custom(dialog,name,color){await dialog.getByRole('button',{name:'Add Custom Option',exact:true}).click();await dialog.getByLabel('Status name',{exact:true}).fill(name);await dialog.getByLabel('Custom HEX color',{exact:true}).fill(color);await dialog.getByRole('button',{name:'Save status option',exact:true}).click();await dialog.getByText('Status option saved.',{exact:true}).waitFor();}
  const nameA='Browser status A '+width;const nameB='Browser status B '+width;
  let da=await add(a);assert.equal(await da.getByLabel('Customer Interest Status',{exact:true}).count(),0);await custom(da,nameA,'#EDE3FF');
  await da.getByLabel('Customer name',{exact:true}).fill('Browser Customer '+width);await da.getByLabel('Customer number',{exact:true}).fill('9000000000');await da.getByLabel('Bank / NBFC',{exact:true}).fill('Browser Bank');
  await da.getByRole('button',{name:'Save record',exact:true}).click();await da.waitFor({state:'hidden'});
  const row=a.getByRole('row').filter({hasText:'Browser Customer '+width});await row.waitFor();
  await a.waitForFunction(name=>[...document.querySelectorAll('tr')].some(row=>row.textContent.includes(name)&&getComputedStyle(row).backgroundColor==='rgb(237, 227, 255)'),'Browser Customer '+width);
  let db=await add(b);await db.getByRole('option',{name:nameA,exact:true}).waitFor({state:'attached'});await custom(db,nameB,'#D9F2F2');
  await row.getByRole('button',{name:'Edit',exact:true}).click();da=a.getByRole('dialog');await da.getByRole('option',{name:nameB,exact:true}).waitFor({state:'attached'});
  await db.getByRole('button',{name:'Manage Options',exact:true}).click();await db.getByRole('button',{name:'Edit color and name for '+nameA,exact:true}).click();await db.getByLabel('Status name',{exact:true}).fill('Renamed A '+width);await db.getByLabel('Custom HEX color',{exact:true}).fill('#112233');await db.getByRole('button',{name:'Save status option',exact:true}).click();
  await db.getByRole('button',{name:'Archive Renamed A '+width,exact:true}).click();await b.getByRole('button',{name:'Archive status',exact:true}).click();await db.getByRole('button',{name:'Restore Renamed A '+width,exact:true}).waitFor();
  await da.getByLabel("Today's case status / remarks",{exact:true}).fill('Edited after status archive');await da.getByRole('button',{name:'Save changes',exact:true}).click();await da.waitFor({state:'hidden'});await row.getByText(nameA,{exact:true}).waitFor();
  await a.waitForFunction(name=>[...document.querySelectorAll('tr')].some(row=>row.textContent.includes(name)&&getComputedStyle(row).backgroundColor==='rgb(17, 34, 51)'&&getComputedStyle(row).color==='rgb(255, 255, 255)'),'Browser Customer '+width);
  await a.screenshot({path:`${output}/colored-table-${width}.png`,fullPage:true});
  await row.getByRole('button',{name:'Edit',exact:true}).click();da=a.getByRole('dialog');await da.getByRole('option',{name:new RegExp(nameA+'.*archived')}).waitFor({state:'attached'});
  await da.getByLabel('Follow-up status',{exact:true}).selectOption({label:nameB});await da.getByRole('button',{name:'Save changes',exact:true}).click();await da.waitFor({state:'hidden'});
  await a.waitForFunction(name=>[...document.querySelectorAll('tr')].some(row=>row.textContent.includes(name)&&getComputedStyle(row).backgroundColor==='rgb(217, 242, 242)'),'Browser Customer '+width);
  await row.getByRole('button',{name:'History',exact:true}).click();await a.getByRole('dialog').getByText(nameA,{exact:false}).first().waitFor();await a.getByRole('button',{name:'Close',exact:true}).click();
  da=await add(a);assert.equal(await da.getByRole('option',{name:new RegExp('Renamed A '+width)}).count(),0);await da.getByRole('button',{name:'Cancel',exact:true}).click();
  await db.getByRole('button',{name:'Edit color and name for FOLLOW UP PENDING',exact:true}).click();assert.equal(await db.getByLabel('Status name',{exact:true}).isDisabled(),true);await db.getByLabel('Custom HEX color',{exact:true}).fill('#FFF0C2');await db.getByLabel('Status color preview',{exact:true}).scrollIntoViewIfNeeded();await b.screenshot({path:`${output}/manage-colors-${width}.png`,fullPage:true});
  assert.equal(await b.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await db.getByRole('button',{name:'Cancel status edit',exact:true}).click();await db.getByRole('button',{name:'Cancel',exact:true}).click();
  await a.reload();await a.getByRole('row').filter({hasText:'Browser Customer '+width}).waitFor();await a.waitForFunction(name=>[...document.querySelectorAll('tr')].some(row=>row.textContent.includes(name)&&getComputedStyle(row).backgroundColor==='rgb(217, 242, 242)'),'Browser Customer '+width);
  assert.deepEqual(errors,[]);results.push({width,result:'passed',backend:'actual FastAPI',database:'isolated local MongoDB',checks:['interest-removed','shared-status-create-select','configured-whole-row-color','rename-archive-history','dark-color-contrast','status-change-immediate-color','default-name-protection','picker-preview','refresh-persistence','mobile-no-page-overflow']});for(const context of contexts)await context.close();
 }
 await writeFile(output+'/results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close();}
