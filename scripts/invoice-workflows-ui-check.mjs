// Browser regression checks against isolated synthetic API fixtures. No production network/data.
import assert from 'node:assert/strict';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {chromium} from '../frontend/node_modules/.cache/voice-ui-audit/node_modules/playwright/index.mjs';

const origin='http://127.0.0.1:5175';
const output='docs/screenshots/invoice-workflow-fixes';
await mkdir(output,{recursive:true});
const pdf=await readFile('docs/invoices/sample-invoice.pdf');
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const results=[];
const envelope=data=>({success:true,data,error:null,meta:null});
const fixture={customer_id:null,customer:{name:'Synthetic Customer',address:'Test Street',city:'Pune',state:'Maharashtra',pincode:'411030',country:'India',gstin:'',phone:'',email:''},invoice_date:'2026-10-30',due_date:'2026-10-30',place_of_supply:'',terms:'',tax_type:'IGST',items:[{description:'Test service',hsn:'9971',quantity:'1',unit:'nos.s',rate:'100',gst_rate:'18'}],subtotal:'100.00',gst_total:'18.00',grand_total:'118.00',amount_in_words:'Synthetic total',version:1,created_by_name:'Synthetic Owner',created_at:'2026-10-30T00:00:00Z'};
const defaults={name:'Synthetic Test Company',address:{line1:'Test Street'},phone:'',email:'',logo_s3_key:null,gstin:'',website:'',bank_name:'Test Bank',branch:'',account_number:'123',account_holder:'Test',ifsc:'',prefix:'INV-',starting_number:1,default_gst:'18',default_terms:'',signatory:'',designation:'',signature_s3_key:null,show_signature:false,qr_type:'none',upi_id:''};
try {
  for(const width of [1440,390]) {
    const context=await browser.newContext({viewport:{width,height:1000},acceptDownloads:true,reducedMotion:'reduce'});
    await context.addInitScript(()=>localStorage.setItem('afs_refresh_token','synthetic-invoice-browser-test'));
    const rows=[];let sequence=3;let reusable=null;let idSequence=3;const writes=[];const errors=[];
    const create=(input,status='draft',number=null)=>{const row={...structuredClone(fixture),...structuredClone(input),id:String(++idSequence).padStart(24,'0'),invoice_number:number||`INV-${String(++sequence).padStart(6,'0')}`,status,version:1};rows.push(row);return row;};
    const original=create({},'issued','INV-000001');const older=create({},'draft','INV-000002');const cancelled=create({},'cancelled','INV-000003');
    const frozen=JSON.stringify(original);
    let role='owner';
    await context.route('**/*',async route=>{
      const req=route.request(),url=new URL(req.url()),path=url.pathname.replace(/^\/api\/v1/,'');
      if(!url.pathname.startsWith('/api/v1/')) return url.origin===origin?route.continue():route.abort();
      const method=req.method();let data=[];const body=method==='GET'?{}:(req.postDataJSON()||{});
      if(path==='/auth/refresh')data={access_token:'synthetic-invoice',refresh_token:'synthetic-invoice'};
      else if(path==='/auth/profile')data={user_id:'aaaaaaaaaaaaaaaaaaaaaaaa',role,name:'Synthetic Staff',mobile:'',must_change_password:false};
      else if(path==='/my-permissions')data={grants:role==='owner'?{}:{'invoices:invoices':['view']}};
      else if(path==='/dashboard/nav')data=[{key:'invoices',label:'Invoices',route:'/invoices',order:1}];
      else if(path.includes('unread-count'))data={count:0};
      else if(path==='/invoices/defaults')data=defaults;
      else if(path==='/invoices/customers')data=[];
      else if(path==='/invoices'&&method==='GET') {const items=rows.filter(r=>!r.is_deleted&&Boolean(r.is_archived)===(url.searchParams.get('archived')==='true'));data={items,total:items.length,total_pages:1};}
      else if(path==='/invoices'&&method==='POST'){const number=reusable;reusable=null;data=create(body,'draft',number);writes.push({method,path,id:data.id});}
      else if(path.startsWith('/invoices/')) {
        const [, ,id,action]=path.split('/');const row=rows.find(r=>r.id===id);assert.ok(row,`Missing synthetic invoice ${path}`);
        if(action==='pdf'){writes.push({method,path,purpose:url.searchParams.get('purpose')});return route.fulfill({contentType:'application/pdf',body:pdf});}
        if(action==='correction')data=rows.find(r=>r.replacement_for===id&&!r.is_deleted)||null;
        else if(action==='delete-options')data={eligible:Number(row.invoice_number.slice(4))===sequence,explanation:'Only the latest unissued draft is eligible; final allocation is decided by the server.'};
        else if(action==='replacement'){data=rows.find(r=>r.replacement_for===id);if(!data)data=create({...row,replacement_for:id,source_invoice_number:row.invoice_number,source_status:row.status,correction_reason:body.reason});writes.push({method,path,id:data.id});}
        else if(action==='duplicate'){data=create({...fixture,customer:row.customer,items:row.items,duplicated_from:id,source_invoice_number:row.invoice_number});writes.push({method,path,id:data.id});}
        else if(action==='archive'){row.is_archived=true;row.archive_reason=body.reason;row.version++;data=row;writes.push({method,path});}
        else if(action==='history')data=[{action:'created',timestamp:fixture.created_at,user_id:'synthetic-owner',new_status:row.status}];
        else if(method==='PUT'){assert.equal(body.version,row.version);Object.assign(row,body,{version:row.version+1});data=row;writes.push({method,path,id:row.id});}
        else if(method==='DELETE'){row.is_deleted=true;if(Number(row.invoice_number.slice(4))===sequence)reusable=row.invoice_number;data={deleted:true,number_reusable:reusable===row.invoice_number,message:'Draft deleted; backend allocation will determine number reuse.'};writes.push({method,path});}
        else data=row;
      }
      return route.fulfill({contentType:'application/json',body:JSON.stringify(envelope(data))});
    });
    const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    async function list(){await page.goto(`${origin}/invoices`);await page.getByRole('heading',{name:'Invoices',exact:true}).waitFor();await page.getByRole('link',{name:'INV-000001',exact:true}).waitFor();}
    async function newInvoice(name){await page.goto(`${origin}/invoices/new`);await page.getByLabel('Customer / Company name',{exact:true}).fill(name);await page.getByLabel('Address',{exact:true}).fill('Synthetic Street');await page.getByLabel('Item 1 description').fill('Synthetic service');await page.getByLabel('Item 1 hsn').fill('9971');await page.getByLabel('Item 1 rate').fill('100');await page.getByRole('button',{name:'Save draft',exact:true}).click();await page.waitForURL(/\/invoices\/[a-f0-9]+$/);return rows.at(-1);}
    async function remove(row){await list();await page.getByLabel(`Actions for ${row.invoice_number}`).selectOption('delete');await page.getByRole('dialog').waitFor();assert.ok(await page.getByText('Customer: Synthetic',{exact:false}).count()||await page.getByText('Customer:',{exact:false}).count());await page.getByRole('button',{name:'Delete Invoice',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});}
    const newest=await newInvoice('Synthetic newest');const newestNumber=newest.invoice_number;
    await page.getByRole('link',{name:'Edit',exact:true}).click();await page.getByLabel('Customer / Company name',{exact:true}).fill('Synthetic edited');await page.getByRole('button',{name:'Save draft',exact:true}).click();await page.waitForURL(/\/invoices\/[a-f0-9]+$/);assert.equal(newest.customer.name,'Synthetic edited');
    await remove(newest);const reused=await newInvoice('Synthetic reused');assert.equal(reused.invoice_number,newestNumber);assert.notEqual(reused.id,newest.id);
    await remove(older);const next=await newInvoice('Synthetic next');assert.notEqual(next.invoice_number,older.invoice_number);assert.notEqual(next.invoice_number,reused.invoice_number);
    await list();await page.getByLabel('Actions for INV-000001').selectOption('duplicate');await page.getByRole('button',{name:'Create New Invoice',exact:true}).click();await page.waitForURL(/\/edit$/);const duplicate=rows.at(-1);assert.equal(duplicate.duplicated_from,original.id);assert.equal(duplicate.replacement_for,undefined);assert.equal(duplicate.status,'draft');
    await list();await page.getByLabel('Actions for INV-000001').selectOption('replacement');await page.getByLabel('Correction reason',{exact:true}).fill('Synthetic correction reason');await page.getByRole('button',{name:'Create Replacement Invoice',exact:true}).click();await page.waitForURL(/\/edit$/);const correction=rows.at(-1);const correctionId=correction.id;
    await page.getByLabel('Customer / Company name',{exact:true}).fill('Synthetic corrected customer');
    for(let i=0;i<2;i++){await page.getByLabel('Item 1 description').fill(`Synthetic correction ${i}`);await page.getByRole('button',{name:'Save draft',exact:true}).click();await page.getByRole('status').filter({hasText:'Correction draft saved'}).waitFor();assert.ok(page.url().includes(correctionId));}
    await list();await page.getByLabel('Actions for INV-000001').selectOption('replacement');await page.getByRole('button',{name:'Resume Correction Draft',exact:true}).click();await page.waitForURL(new RegExp(`${correctionId}/edit$`));assert.equal(await page.getByLabel('Customer / Company name',{exact:true}).inputValue(),'Synthetic corrected customer');assert.equal(rows.filter(r=>r.replacement_for===original.id).length,1);assert.equal(JSON.stringify(original),frozen);
    await page.screenshot({path:`${output}/correction-${width}.png`,fullPage:true});
    await page.goto(`${origin}/invoices/${original.id}`);await page.getByTitle('Invoice PDF',{exact:true}).waitFor();const download=page.waitForEvent('download');await page.getByRole('button',{name:'Download PDF',exact:true}).click();assert.equal((await download).suggestedFilename(),'INV-000001.pdf');await page.getByRole('button',{name:'Print',exact:true}).click();assert.ok(writes.some(w=>w.purpose==='print'));
    for(const row of [cancelled,original]){await list();await page.getByLabel(`Actions for ${row.invoice_number}`).selectOption('archive');await page.getByLabel('Archive reason',{exact:true}).fill('Synthetic archive');await page.getByRole('button',{name:'Archive Invoice',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});assert.equal(row.status,row===original?'issued':'cancelled');}
    await page.getByLabel('Archived invoices',{exact:true}).check();await page.getByRole('link',{name:'INV-000001',exact:true}).waitFor();
    role='employee';await page.reload();await page.getByRole('heading',{name:'Invoices',exact:true}).waitFor();assert.equal(await page.getByRole('link',{name:'Create invoice',exact:true}).count(),0);assert.equal(await page.getByRole('option',{name:'Delete',exact:true}).count(),0);assert.equal(await page.getByRole('option',{name:'Archive',exact:true}).count(),0);
    assert.deepEqual(errors,[]);results.push({width,result:'passed',synthetic:true,correctionId,correctionCount:1,putSaves:writes.filter(w=>w.method==='PUT').length,checks:['create','edit','latest-delete-reuse','older-gap-not-reused','duplicate','correction-repeat-save','resume-correction','source-immutable','download','print-request','archive-issued-cancelled','employee-permissions']});await context.close();
  }
  await writeFile(`${output}/results.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
} finally {await browser.close();}
