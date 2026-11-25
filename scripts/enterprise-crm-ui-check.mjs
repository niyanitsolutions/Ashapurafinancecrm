import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium} from '../frontend/node_modules/.cache/voice-ui-audit/node_modules/playwright/index.mjs';
const fixture=JSON.parse(process.env.AFS_ASSIGNMENT_FIXTURE);
const output='docs/screenshots/enterprise-crm-2026-11-25';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const results=[];let currentPage;let stage='start';
try {
 for(const width of [390,768,1366]) {
  const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});
  await context.route('**/api/v1/**',async route=>{try{const u=new URL(route.request().url());const response=await route.fetch({url:'http://127.0.0.1:18773'+u.pathname+u.search});await route.fulfill({response});}catch(error){if(!/Route is already handled|Fetch response has been disposed|Target page, context or browser has been closed/.test(error.message))throw error;}});
  await context.route('https://**',route=>route.abort());
  const page=await context.newPage();currentPage=page;stage=`login-${width}`;
  await page.goto('http://127.0.0.1:5175/login');await page.getByRole('tab',{name:'Employee / Partner',exact:true}).click();
  await page.locator('#internal-mobile').fill('9000080000');await page.locator('#internal-password').fill('InitialPass1!');await page.getByRole('button',{name:'Log in',exact:true}).click();await page.waitForURL('**/dashboard');
  stage=`grouped-${width}`;await page.goto('http://127.0.0.1:5175/leads/document-collection');
  await page.getByRole('button',{name:'Expand',exact:true}).click();await page.getByRole('link',{name:'TEST-APPLICATION',exact:true}).first().waitFor();
  assert.equal(await page.locator('select').filter({has:page.locator('option[value="200"]')}).inputValue(),'200');
  await page.getByText('Advanced filters',{exact:true}).click();await page.screenshot({path:`${output}/filters-${width}.png`,fullPage:true});
  await page.getByRole('button',{name:'Apply Filters',exact:true}).click();await page.getByRole('button',{name:'Collapse',exact:true}).waitFor();
  const search=page.getByRole('combobox',{name:'Search CRM'}).filter({visible:true});
  stage=`search-${width}`;await search.fill('TEST-APPLICATION');await page.getByRole('option').filter({hasText:'TEST-APPLICATION'}).first().click();await page.waitForURL(url=>url.pathname===`/applications/${fixture.app_id}`);
  await page.getByRole('heading',{name:'Customer Details - current profile',exact:true}).waitFor();
  stage=`profile-${width}`;await page.getByRole('button',{name:'Edit Customer Details',exact:true}).click();
  const dialog=page.getByRole('dialog');await dialog.getByLabel('Full name',{exact:true}).fill(`Edited Customer ${width}`);await dialog.getByLabel('Reason for change',{exact:true}).fill('Synthetic browser verification');await page.waitForTimeout(350);const profileBox=await dialog.boundingBox();assert(profileBox && profileBox.x>=0 && profileBox.y>=-1 && profileBox.x+profileBox.width<=width+1 && profileBox.y+profileBox.height<=1001);await page.screenshot({path:`${output}/profile-edit-${width}.png`});await dialog.getByRole('button',{name:'Save profile',exact:true}).click();await dialog.waitFor({state:'hidden'});
  await page.getByText(`Edited Customer ${width}`,{exact:true}).waitFor();await page.screenshot({path:`${output}/profile-${width}.png`,fullPage:true});
  stage=`delete-${width}`;await page.goto('http://127.0.0.1:5175/leads/document-collection');await page.getByRole('button',{name:'Expand',exact:true}).click();await page.getByRole('button',{name:'Delete application',exact:true}).click();await page.getByRole('dialog').waitFor();await page.waitForTimeout(350);const deleteBox=await page.getByRole("dialog").boundingBox();assert(deleteBox && deleteBox.x>=0 && deleteBox.y>=-1 && deleteBox.x+deleteBox.width<=width+1 && deleteBox.y+deleteBox.height<=1001);await page.screenshot({path:`${output}/delete-${width}.png`});
  if(width===1366) { await page.getByRole('button',{name:'Confirm Delete',exact:true}).click();await page.getByText('No matching customers or applications.',{exact:true}).waitFor(); }
  else await page.getByRole('button',{name:'Cancel',exact:true}).click();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  results.push({width,result:'passed',journeys:['grouped expansion','default 200','filters','authorized global search','versioned profile edit','Owner delete confirmation']});
  await context.unrouteAll({behavior:'ignoreErrors'});await context.close();
 }
 await writeFile(`${output}/results.json`,JSON.stringify({results,backend:'real local API and disposable MongoDB',external_calls:'none'},null,2));
 console.log('Enterprise browser checks passed at all three widths.');
} catch(e) { if(currentPage) await currentPage.screenshot({path:`${output}/failure.png`,fullPage:true}).catch(()=>{}); console.error(`Failed at ${stage}: ${e.message}`);throw e; }
finally { await browser.close(); }
