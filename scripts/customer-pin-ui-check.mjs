import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {createInterface} from 'node:readline/promises';
import {chromium} from '../frontend/node_modules/.cache/voice-ui-audit/node_modules/playwright/index.mjs';

const origin='http://127.0.0.1:5175';
const output=process.env.AFS_PIN_BROWSER_OUTPUT || 'docs/screenshots/customer-portal-modernisation/registration';
const widths=JSON.parse(process.env.AFS_PIN_BROWSER_WIDTHS || '[1440,390]');
await mkdir(output,{recursive:true});
const input=createInterface({input:process.stdin,terminal:false});
async function code() { console.log('NEED_MOCK_OTP'); return new Promise(resolve=>input.once('line',resolve)); }
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const results=[];
let stage='start';
try {
 for (const [index,width] of widths.entries()) {
  const mobile='90000000'+(88+index);
  const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});
  const errors=[];
  await context.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(!url.pathname.startsWith('/api/v1/')) return url.origin===origin ? route.continue() : route.abort();
    try {
      const response=await route.fetch({url:'http://127.0.0.1:18770'+url.pathname+url.search});
      await route.fulfill({response});
    } catch { await route.abort().catch(()=>{}); }
  });
  const page=await context.newPage(); page.on('pageerror',e=>errors.push(e.message));
  stage=`register-${width}`; await page.goto(origin+'/register');
  await page.getByLabel('Mobile Number',{exact:true}).waitFor();
  assert.equal(await page.locator('input').count(),4);
  assert.equal(await page.getByLabel('Create 4-Digit PIN',{exact:true}).getAttribute('type'),'password');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:`${output}/register-${width}.png`,fullPage:true,animations:'disabled'});
  await page.getByLabel('Mobile Number',{exact:true}).fill(mobile);
  if(index===0) await page.getByLabel('Email Address (optional)',{exact:true}).fill('browser@example.com');
  await page.getByLabel('Create 4-Digit PIN',{exact:true}).fill('0472');
  await page.getByLabel('Confirm 4-Digit PIN',{exact:true}).fill('0472');
  stage=`registration-otp-${width}`; await page.getByRole('button',{name:'Send OTP',exact:true}).click();
  await page.getByLabel('4-digit SMS OTP',{exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:/Resend OTP in/}).isDisabled(),true);
  await page.getByLabel('4-digit SMS OTP',{exact:true}).fill(await code());
  await page.getByRole('button',{name:'Verify OTP',exact:true}).click();
  stage=`complete-${width}`; await page.getByRole('button',{name:'Complete Registration',exact:true}).click();
  await page.waitForURL('**/portal');
  await page.evaluate(()=>localStorage.clear());
  await page.goto(origin+'/login');
  await page.getByRole('tab',{name:'Employee / Partner',exact:true}).click();
  assert.equal(await page.locator('#internal-password').isVisible(),true);
  await page.getByRole('tab',{name:'Customer',exact:true}).click();
  assert.equal(await page.locator('#internal-password').isVisible(),false);
  await page.screenshot({path:`${output}/login-${width}.png`,fullPage:true,animations:'disabled'});
  stage=`login-${width}`; await page.getByLabel('Registered mobile number',{exact:true}).fill(mobile);
  await page.getByLabel('4-digit PIN',{exact:true}).fill('0472');
  await page.getByRole('button',{name:'Log in',exact:true}).click();
  await page.waitForURL('**/portal');
  // New unauthenticated context for recovery; the existing session is revoked by reset.
  await page.evaluate(()=>localStorage.clear());
  await page.goto(origin+'/login');
  stage=`forgot-${width}`; await page.getByRole('button',{name:'Forgot PIN',exact:true}).click();
  await page.getByLabel('Registered mobile number',{exact:true}).fill(mobile);
  await page.getByRole('button',{name:'Send verification code',exact:true}).click();
  await page.getByLabel('4-digit OTP',{exact:true}).fill(await code());
  await page.getByRole('button',{name:'Verify OTP',exact:true}).click();
  await page.getByLabel('New 4-digit PIN',{exact:true}).fill('5938');
  await page.getByLabel('Confirm PIN',{exact:true}).fill('5938');
  stage=`reset-${width}`; await page.getByRole('button',{name:'Save PIN',exact:true}).click();
  await page.getByRole('button',{name:'Return to login',exact:true}).click();
  await page.getByLabel('4-digit PIN',{exact:true}).fill('0472');
  const rejected=page.waitForResponse(r=>r.url().includes('/auth/pin/login') && r.status()===401);
  await page.getByRole('button',{name:'Log in',exact:true}).click(); await rejected;
  await page.getByLabel('4-digit PIN',{exact:true}).fill('5938');
  await page.getByRole('button',{name:'Log in',exact:true}).click();
  await page.waitForURL('**/portal');
  assert.deepEqual(errors,[]);
  assert.equal(await page.evaluate(()=>Object.keys(localStorage).some(key=>/pin|otp/i.test(key))),false);
  results.push({width,result:'passed',provider:'mocked; no SMS',checks:['four-field-registration','optional-email','otp-before-account','mobile-pin-login','forgot-pin','old-pin-rejected','new-pin-login','staff-password-tab-preserved','no-page-overflow','no-runtime-errors']});
  await context.unrouteAll({behavior:'ignoreErrors'}); await context.close();
 }
 await writeFile(output+'/results.json',JSON.stringify(results,null,2));
 console.log(JSON.stringify(results));
} catch(error) {
  console.error(`${stage}: ${error.name}: ${String(error.message).split('\n')[0]}`);
  process.exitCode=1;
} finally { input.close(); await browser.close(); }
