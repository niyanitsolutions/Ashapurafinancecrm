import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium} from '../frontend/node_modules/.cache/voice-ui-audit/node_modules/playwright/index.mjs';

const origin='http://127.0.0.1:5175';
const fixture=JSON.parse(process.env.AFS_PORTAL_FIXTURE);
const output='docs/screenshots/customer-portal-modernisation';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const results=[];let stage='start';let applicationId;
let currentPage;const apiFailures=[];
async function connect(context){
 await context.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname.startsWith('/api/v1/')){
   try {const response=await route.fetch({url:'http://127.0.0.1:18771'+url.pathname+url.search});await route.fulfill({response});}
   catch {await route.abort().catch(()=>{});} return;
  }
  if(url.hostname.endsWith('amazonaws.com')) return route.fulfill({status:200,body:'mocked private storage'});
  return url.origin===origin ? route.continue() : route.abort();
 });
}
async function capture(page,name,width){
 await page.evaluate(()=>document.fonts.ready);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${name} overflow at ${width}`);
 await page.screenshot({path:`${output}/${name}-${width}.png`,fullPage:true,animations:'disabled'});
}
async function pinLogin(page,width){
 await page.goto(origin+'/login');
 await page.getByLabel('4-digit PIN',{exact:true}).waitFor();await capture(page,'customer-login',width);
 await page.getByRole('button',{name:'Show PIN',exact:true}).click();assert.equal(await page.getByLabel('4-digit PIN',{exact:true}).getAttribute('type'),'text');
 await page.getByRole('button',{name:'Hide PIN',exact:true}).click();
 await page.getByLabel('Registered mobile number',{exact:true}).fill('9000000098');
 await page.getByLabel('4-digit PIN',{exact:true}).fill('0472');
 await page.getByRole('button',{name:'Log in',exact:true}).click();await page.waitForURL('**/portal');
}
try{
 for(const width of [360,390,768,1024,1366,1920]){
  stage=`overview-${width}`;const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});await connect(context);
  const page=await context.newPage();currentPage=page;const errors=[];page.on('pageerror',e=>errors.push(e.name));
  page.on('response',response=>{if(response.status()>=400 && response.url().includes('/api/v1/'))apiFailures.push({path:new URL(response.url()).pathname,status:response.status()});});
  await pinLogin(page,width);await page.getByRole('heading',{name:/Welcome/}).waitFor();await page.getByText('Your applications',{exact:true}).waitFor();
  await capture(page,'overview',width);
  if(width===390){stage='notification-menu';await page.getByRole('button',{name:'Notifications',exact:true}).click();await page.getByRole('link',{name:'View All',exact:true}).waitFor();await capture(page,'notification-menu',width);await page.getByRole('button',{name:'Notifications',exact:true}).click();}
  if(width===360){
   stage='independent-start';await page.getByRole('link',{name:'Apply for loan',exact:true}).click();
   await page.getByRole('button',{name:/Portal Personal Loan/}).click();await page.waitForURL(/\/portal\/applications\/[a-f0-9]{24}$/);applicationId=page.url().split('/').pop();
   await page.getByLabel(/Loan Amount/).fill('50000');
   await page.getByRole('button',{name:'Save and continue later',exact:true}).click();await page.waitForURL('**/portal/applications');
   stage='resume';await page.goto(origin+'/portal/applications/'+applicationId);assert.equal(await page.getByLabel(/Loan Amount/).inputValue(),'50000');
   stage='unsaved-navigation';await page.getByLabel(/Loan Amount/).fill('51000');await page.getByRole('button',{name:/Back to My Applications/}).click();
   await page.getByRole('button',{name:'Save and leave',exact:true}).click();await page.waitForURL('**/portal/applications');
   await page.goto(origin+'/portal/applications/'+applicationId);assert.equal(await page.getByLabel(/Loan Amount/).inputValue(),'51000');
   await page.getByRole('button',{name:'Continue',exact:true}).click();
   stage='document-upload';await page.locator('input[type=file]').first().setInputFiles({name:'test.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4 mocked fixture')});
   await page.getByText('test.pdf',{exact:true}).waitFor();await page.getByRole('button',{name:'Continue',exact:true}).click();
   stage='submit';await page.getByRole('button',{name:'Submit Application',exact:true}).click();await page.getByRole('button',{name:'Confirm submission',exact:true}).click();await page.waitForURL('**/portal/applications');
   stage='secure-link';await page.goto(origin+'/apply/'+fixture.secure_code);await page.getByRole('button',{name:'Continue Application',exact:true}).click();await page.waitForURL(/\/portal\/applications\/[a-f0-9]{24}$/);
   assert.notEqual(page.url().split('/').pop(),applicationId);
   const secureApplication=page.url();await page.goto(origin+'/apply/'+fixture.secure_code);await page.getByRole('button',{name:'Continue Application',exact:true}).click();await page.waitForURL(secureApplication);
   stage='expired-link';await page.goto(origin+'/apply/EXPIREDPORTAL');await page.getByRole('heading',{name:'Application Link Expired',exact:true}).waitFor();await capture(page,'expired-link',width);
   stage='disabled-link';await page.goto(origin+'/apply/DISABLEDPORTAL');await page.getByRole('heading',{name:'Link Invalid',exact:true}).waitFor();await capture(page,'disabled-link',width);
  }
  stage=`applications-${width}`;await page.goto(origin+'/portal/applications');await page.getByRole('heading',{name:'My applications',exact:true}).waitFor();await capture(page,'applications',width);
  stage=`form-${width}`;await page.goto(origin+'/portal/applications/'+fixture.staff_id);await page.getByLabel(/Loan Amount/).waitFor();await capture(page,'guided-form',width);
  stage=`documents-${width}`;await page.goto(origin+'/portal/documents');await page.getByRole('heading',{name:'Document Center',exact:true}).waitFor();await page.getByText('test.pdf',{exact:true}).waitFor();await capture(page,'documents',width);
  if(width===390){stage='document-history';await page.getByRole('button',{name:/PAN.*version history/}).click();await page.getByRole('region',{name:/PAN.*version history/}).waitFor();await capture(page,'document-history',width);await page.getByRole('button',{name:'Close history',exact:true}).click();}
  if(width===390 || width===1366){
   for(const [path,title] of [['profile','My Profile'],['messages','Message your RM'],['alerts','Notifications'],['support','Support']]){
    stage=`${path}-${width}`;await page.goto(origin+'/portal/'+path);await page.locator('h1').first().waitFor();await capture(page,path,width);
   }
  }
  if(width<768){stage=`mobile-navigation-${width}`;await page.getByRole('button',{name:'Customer navigation',exact:true}).click();assert.equal(await page.getByRole('navigation',{name:'Customer mobile navigation'}).isVisible(),true);await capture(page,'mobile-navigation',width);}
  assert.deepEqual(errors,[]);results.push({width,result:'passed',api:'real local FastAPI; mocked storage; no SMS'});
  await context.unrouteAll({behavior:'ignoreErrors'});await context.close();
 }
 stage='staff-document-collection';const context=await browser.newContext({viewport:{width:1366,height:1000}});await connect(context);const page=await context.newPage();
 await page.goto(origin+'/login');await page.getByRole('tab',{name:'Employee / Partner',exact:true}).click();await page.locator('#internal-mobile').fill('9000000001');await page.locator('#internal-password').fill('OwnerPass1!');await page.getByRole('button',{name:'Log in',exact:true}).click();await page.waitForURL('**/dashboard');
 await page.goto(origin+'/leads/document-collection');await page.getByText('Customer submitted',{exact:true}).first().waitFor();await capture(page,'existing-document-collection',1366);
 await context.unrouteAll({behavior:'ignoreErrors'});await context.close();
 await writeFile(output+'/results.json',JSON.stringify({viewports:results,journeys:['PIN login','save/resume','private upload','confirmed submission','secure-link same application resume','staff Document Collection'],providers:'mocked; no SMS'},null,2));console.log(JSON.stringify(results));
}catch(error){console.error(`${stage}: ${error.name}: ${String(error.message).split('\n')[0]}`);console.error(JSON.stringify(apiFailures));if(currentPage)await currentPage.screenshot({path:output+'/failed.png',fullPage:true,animations:'disabled'}).catch(()=>{});process.exitCode=1;}
finally{await browser.close();}
