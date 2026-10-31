import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";
import { ApiError } from "@/shared/api/client";
import { InvoiceListPage } from "./InvoiceListPage";
import { InvoiceFormPage } from "./InvoiceFormPage";
import { InvoiceViewPage } from "./InvoiceViewPage";
import { InvoiceWorkflow } from "./InvoiceWorkflow";
import { InvoiceSettingsPage } from "./InvoiceSettingsPage";

const permissions=vi.hoisted(()=>({create:true,edit:true,owner:true}));
vi.mock("@/features/access_control/usePermissions",()=>({usePermissions:()=>({isOwner:permissions.owner,can:(_key: string,action: string)=>action==="view"||permissions[action as "create"|"edit"]})}));
vi.mock("./api",async original=>({...await original<typeof import("./api")>(),listInvoices:vi.fn(),getDefaults:vi.fn(),getCustomers:vi.fn(),saveInvoice:vi.fn(),previewPdf:vi.fn(),getInvoice:vi.fn(),invoicePdf:vi.fn(),setInvoiceStatus:vi.fn(),duplicateInvoice:vi.fn(),getSettings:vi.fn(),saveSettings:vi.fn(),uploadSignature:vi.fn(),downloadPdf:vi.fn(),deleteInvoice:vi.fn(),replacementInvoice:vi.fn(),invoiceHistory:vi.fn(),getCorrectionDraft:vi.fn(),getDeleteOptions:vi.fn(),archiveInvoice:vi.fn(),getInvoiceRevisions:vi.fn(),historicalInvoicePdf:vi.fn(),requestRevision:vi.fn(),reissueInvoice:vi.fn(),deleteIssuedInvoice:vi.fn(),previewRevisionPdf:vi.fn()}));
const fixture={id:"i1",invoice_number:"INV-000001",customer_id:null,customer:{name:"Acme",address:"Street",city:"Pune",state:"Maharashtra",pincode:"411030",country:"India",gstin:"",phone:"",email:""},invoice_date:"2026-10-04",due_date:"2026-10-04",place_of_supply:"",terms:"",tax_type:"IGST" as const,version:1,status:"draft" as const,items:[{description:"Consultancy",hsn:"9971",quantity:"3",unit:"nos.s",rate:"7753.71",gst_rate:"18"}],subtotal:"23261.13",gst_total:"4187.00",grand_total:"27448.13",amount_in_words:"Words",created_by_name:"Owner",created_at:"2026-10-04T00:00:00Z"};
beforeEach(()=>{
  vi.clearAllMocks();permissions.create=true;permissions.edit=true;permissions.owner=true;
  vi.stubGlobal("URL",Object.assign(URL,{createObjectURL:vi.fn(()=>"blob:invoice"),revokeObjectURL:vi.fn()}));
  vi.mocked(api.listInvoices).mockResolvedValue({items:[fixture],total:1,total_pages:1});
  vi.mocked(api.getDefaults).mockResolvedValue({default_gst:"18",default_terms:"",bank_name:"Bank"} as api.Company);
  vi.mocked(api.getCustomers).mockResolvedValue([]);vi.mocked(api.getInvoice).mockResolvedValue(fixture);
  vi.mocked(api.invoicePdf).mockResolvedValue(new Blob(["pdf"]));vi.mocked(api.previewPdf).mockResolvedValue(new Blob(["preview"]));
  vi.mocked(api.saveInvoice).mockResolvedValue(fixture);
  vi.mocked(api.getCorrectionDraft).mockResolvedValue(null);
  vi.mocked(api.getDeleteOptions).mockResolvedValue({eligible:true,explanation:"Eligible only while latest; this is not a reservation."});
  vi.mocked(api.invoiceHistory).mockResolvedValue([]);
  vi.mocked(api.getInvoiceRevisions).mockResolvedValue([]);
  vi.mocked(api.historicalInvoicePdf).mockResolvedValue(new Blob(["historical"]));
});
function show(element: React.ReactNode,path="/") {render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/" element={element}/><Route path="/invoices" element={<p>Invoice list</p>}/><Route path="/invoices/:invoiceId/edit" element={element}/><Route path="/invoices/:invoiceId" element={path==="/"?<p>Saved invoice</p>:element}/></Routes></MemoryRouter>);}
describe("invoice screens",()=>{
  it("lists invoices and applies search filters",async()=>{
    show(<InvoiceListPage/>);expect(await screen.findByText("INV-000001")).toBeInTheDocument();
    const user=userEvent.setup();await user.type(screen.getByLabelText("Search invoices"),"Acme");
    await waitFor(()=>expect(vi.mocked(api.listInvoices).mock.lastCall?.[0].get("search")).toBe("Acme"));
  });
  it("hides create and edit without permissions",async()=>{
    permissions.create=false;permissions.edit=false;show(<InvoiceListPage/>);
    await screen.findByText("INV-000001");expect(screen.queryByText("Create invoice")).not.toBeInTheDocument();expect(screen.queryByText("Edit")).not.toBeInTheDocument();
  });
  it("adds/removes items and prevents saving missing required fields",async()=>{
    show(<InvoiceFormPage/>);const user=userEvent.setup();await screen.findByText("Invoice details");
    await user.click(screen.getByRole("button",{name:"+ Add item"}));expect(screen.getAllByLabelText(/Item \d description/)).toHaveLength(2);
    await user.click(screen.getAllByRole("button",{name:"Remove"})[1]);expect(screen.getAllByLabelText(/Item \d description/)).toHaveLength(1);
    await user.click(screen.getByRole("button",{name:"Save draft"}));expect(api.saveInvoice).not.toHaveBeenCalled();
  });
  it("previews and saves a draft using input data without submitted totals",async()=>{
    show(<InvoiceFormPage/>,"/invoices/i1/edit");const user=userEvent.setup();await screen.findByDisplayValue("Consultancy");
    expect(screen.getAllByText("₹27,448.13").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button",{name:"Preview invoice"}));expect(await screen.findByTitle("Invoice preview")).toHaveAttribute("src","blob:invoice");
    await user.click(screen.getByRole("button",{name:"Save draft"}));await waitFor(()=>expect(api.saveInvoice).toHaveBeenCalled());
    expect(vi.mocked(api.saveInvoice).mock.calls[0][0]).not.toHaveProperty("grand_total");
  });
  it("shows the shared PDF and requires a cancellation reason",async()=>{
    vi.mocked(api.setInvoiceStatus).mockResolvedValue({...fixture,status:"cancelled"});
    show(<InvoiceViewPage/>,"/invoices/i1");const user=userEvent.setup();await screen.findByTitle("Invoice PDF");
    await user.click(screen.getByRole("button",{name:"Cancel invoice"}));await user.click(screen.getByRole("button",{name:"Confirm cancellation"}));expect(api.setInvoiceStatus).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText("Cancellation reason"),"Correction required");await user.click(screen.getByRole("button",{name:"Confirm cancellation"}));
    await waitFor(()=>expect(api.setInvoiceStatus).toHaveBeenCalledWith("i1","cancelled",1,"Correction required"));
  });
  it("protects issued fields and performs status and download actions",async()=>{
    vi.mocked(api.getInvoice).mockResolvedValue({...fixture,status:"issued",version:2});
    vi.mocked(api.setInvoiceStatus).mockResolvedValue({...fixture,status:"paid",version:3});
    show(<InvoiceViewPage/>,"/invoices/i1");const user=userEvent.setup();await screen.findByTitle("Invoice PDF");
    expect(screen.queryByRole("link",{name:"Edit"})).not.toBeInTheDocument();expect(screen.getByRole("button",{name:"Edit"})).toBeInTheDocument();expect(screen.queryByText("Issue invoice")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button",{name:"Download PDF"}));await waitFor(()=>expect(api.invoicePdf).toHaveBeenCalledWith("i1","download"));
    await user.click(screen.getByRole("button",{name:"Mark paid"}));await waitFor(()=>expect(api.setInvoiceStatus).toHaveBeenCalledWith("i1","paid",2,""));
  });
  it("configures bank and QR settings through the existing settings area",async()=>{
    const config: api.InvoiceConfig={gstin:"",website:"",bank_name:"Bank",branch:"",account_number:"",account_holder:"",ifsc:"",prefix:"INV-",starting_number:1,default_gst:"18",default_terms:"",signatory:"",designation:"",signature_s3_key:null,show_signature:true,qr_type:"none",upi_id:""};
    vi.mocked(api.getSettings).mockResolvedValue({config,company:{...config,name:"Ashapura Financial Services"} as api.Company,assets:{logo:null,signature:null}});
    vi.mocked(api.saveSettings).mockResolvedValue({...config,qr_type:"upi",upi_id:"example@bank"});
    show(<InvoiceSettingsPage/>);const user=userEvent.setup();await screen.findByDisplayValue("Bank");
    await user.selectOptions(screen.getByLabelText("QR type"),"upi");await user.click(screen.getByRole("button",{name:"Save invoice settings"}));expect(api.saveSettings).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText("UPI ID"),"example@bank");await user.click(screen.getByRole("button",{name:"Save invoice settings"}));
    expect(await screen.findByRole("status")).toHaveTextContent("Invoice settings saved");expect(api.saveSettings).toHaveBeenCalledWith(expect.objectContaining({bank_name:"Bank",qr_type:"upi",upi_id:"example@bank"}));
  });
});


describe("invoice workflows",()=>{
  it("requires confirmation and preserves errors when deletion fails",async()=>{
    vi.mocked(api.deleteInvoice).mockRejectedValue(new ApiError("conflict", "Invoice changed. Reload before saving."));
    show(<InvoiceListPage/>);const user=userEvent.setup();await screen.findByText("INV-000001");
    await user.selectOptions(screen.getByLabelText("Actions for INV-000001"),"delete");
    expect(api.deleteInvoice).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button",{name:"Delete Invoice"}));
    expect(await screen.findByText("Invoice changed. Reload before saving.")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
  it("keeps duplication independent of same-number revisions",async()=>{
    show(<InvoiceWorkflow invoice={fixture} mode="duplicate" onClose={()=>{}} onDeleted={()=>{}}/>);const user=userEvent.setup();
    expect(screen.getByRole("button",{name:"Create New Invoice"})).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Create Revision of Existing Invoice"})).not.toBeInTheDocument();
    expect(api.duplicateInvoice).not.toHaveBeenCalled();await user.click(screen.getByRole("button",{name:"Cancel / Close"}));
  });
  it("requires a reason for a replacement and keeps the original visible",async()=>{
    vi.mocked(api.getInvoice).mockResolvedValue({...fixture,status:"issued"});
    vi.mocked(api.replacementInvoice).mockRejectedValue(new ApiError("conflict", "Please retry"));
    show(<InvoiceWorkflow invoice={{...fixture,status:"issued"}} mode="replacement" onClose={()=>{}} onDeleted={()=>{}}/>);const user=userEvent.setup();
    expect(screen.getByRole("button",{name:"Create Replacement Invoice"})).toBeDisabled();
    await user.type(screen.getByLabelText("Correction reason"),"Correct amount");
    await user.click(screen.getByRole("button",{name:"Create Replacement Invoice"}));
    await waitFor(()=>expect(api.replacementInvoice).toHaveBeenCalledWith("i1","Correct amount",expect.any(String)));
    expect(await screen.findByText("Please retry")).toBeInTheDocument();
  });
  it("hides destructive and copying actions for settled invoices",async()=>{
    vi.mocked(api.listInvoices).mockResolvedValue({items:[{...fixture,status:"paid"}],total:1,total_pages:1});
    show(<InvoiceListPage/>);await screen.findByText("INV-000001");
    for(const name of ["Delete","Duplicate","Cancel","Create Correction / Replacement"])
      expect(screen.queryByRole("option",{name})).not.toBeInTheDocument();
  });
});

describe('correction persistence and archive',()=>{
  it('resumes an existing correction without another creation request',async()=>{
    vi.mocked(api.getInvoice).mockResolvedValue({...fixture,status:'issued'});
    vi.mocked(api.getCorrectionDraft).mockResolvedValue({...fixture,id:'c1',invoice_number:'INV-000002',replacement_for:'i1',source_invoice_number:fixture.invoice_number,correction_reason:'Correct amount'});
    show(<InvoiceWorkflow invoice={{...fixture,status:"issued"}} mode="replacement" onClose={()=>{}} onDeleted={()=>{}}/>);const user=userEvent.setup();
    expect(await screen.findByRole('button',{name:'Resume Correction Draft'})).toBeEnabled();
    expect(screen.getByLabelText('Correction reason')).toHaveValue('Correct amount');
    await user.click(screen.getByRole('button',{name:'Resume Correction Draft'}));
    expect(api.replacementInvoice).not.toHaveBeenCalled();
  });
  it('keeps correction identity and server version across repeated saves',async()=>{
    const correction={...fixture,replacement_for:'original',source_invoice_number:'INV-000000',source_status:'issued',correction_reason:'Correct amount'};
    vi.mocked(api.getInvoice).mockResolvedValue(correction);
    vi.mocked(api.saveInvoice).mockResolvedValueOnce({...correction,version:2}).mockResolvedValueOnce({...correction,version:3});
    show(<InvoiceFormPage/>,'/invoices/i1/edit');const user=userEvent.setup();await screen.findByDisplayValue('Consultancy');
    await user.click(screen.getByRole('button',{name:'Save draft'}));
    expect(await screen.findByRole('status')).toHaveTextContent('Correction draft saved: INV-000001');
    await user.click(screen.getByRole('button',{name:'Save draft'}));
    await waitFor(()=>expect(api.saveInvoice).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.saveInvoice).mock.calls.map(([input,id])=>[id,input.version])).toEqual([['i1',1],['i1',2]]);
    expect(screen.getByRole('heading',{name:'Edit correction draft'})).toBeInTheDocument();
  });
  it('requires an archive reason and refreshes the list on success',async()=>{
    vi.mocked(api.listInvoices).mockResolvedValueOnce({items:[{...fixture,status:'cancelled'}],total:1,total_pages:1}).mockResolvedValue({items:[],total:0,total_pages:1});
    vi.mocked(api.archiveInvoice).mockResolvedValue({...fixture,status:'issued',is_archived:true});
    show(<InvoiceListPage/>);const user=userEvent.setup();await screen.findByText('INV-000001');
    await user.selectOptions(screen.getByLabelText('Actions for INV-000001'),'archive');
    expect(screen.getByRole('button',{name:'Archive Invoice'})).toBeDisabled();
    await user.type(screen.getByLabelText('Archive reason'),'Retain for review');
    await user.click(screen.getByRole('button',{name:'Archive Invoice'}));
    expect(api.archiveInvoice).toHaveBeenCalledWith('i1',1,'Retain for review');
    expect(await screen.findByText('No invoices found.')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Invoice archived');
  });
  it('filters archived invoices without changing other list filters',async()=>{
    show(<InvoiceListPage/>);const user=userEvent.setup();await screen.findByText('INV-000001');
    await user.click(screen.getByLabelText('Archived invoices'));
    await waitFor(()=>expect(vi.mocked(api.listInvoices).mock.lastCall?.[0].get('archived')).toBe('true'));
  });
});

describe('same-number issued invoice revisions',()=>{
  const issued={...fixture,status:'issued' as const,version:2,effective_revision:1,issued_at:'2026-10-04T12:00:00Z'};
  it('shows status-specific list actions and keeps archived records view-only',async()=>{
    vi.mocked(api.listInvoices).mockResolvedValue({items:[issued],total:1,total_pages:1});
    show(<InvoiceListPage/>);await screen.findByText('INV-000001');
    expect(screen.getAllByRole('option').filter(o=>o.parentElement?.getAttribute('aria-label')==='Actions for INV-000001').map(o=>o.textContent)).toEqual(['Actions','View','Edit','Delete']);
  });
  it('blocks Edit & Reissue while policy is disabled',async()=>{
    vi.mocked(api.getInvoice).mockResolvedValue(issued);
    show(<InvoiceViewPage/>,'/invoices/i1');const user=userEvent.setup();await screen.findByTitle('Invoice PDF');
    await user.click(screen.getByRole('button',{name:'Edit'}));
    expect(await screen.findByRole('dialog')).toHaveTextContent('Edit Issued Invoice');
    expect(await screen.findByText(/Same-number reissue is disabled/)).toBeInTheDocument();
    expect(screen.getByRole('button',{name:'Edit & Reissue'})).toBeDisabled();
    expect(api.replacementInvoice).not.toHaveBeenCalled();expect(api.requestRevision).not.toHaveBeenCalled();
  });
  it('saves proposals against the original ID and requires reason and owner approval',async()=>{
    vi.mocked(api.getDefaults).mockResolvedValue({default_gst:'18',same_number_reissue_enabled:true} as api.Company);
    vi.mocked(api.getInvoice).mockResolvedValue(issued);
    const pending={...issued,version:3,revision_proposal:{id:'proposal-1',status:'pending_owner_approval',reason:'Correct amount',snapshot:issued,requested_by:'owner',requested_at:'2026-10-31T00:00:00Z'}};
    vi.mocked(api.requestRevision).mockResolvedValue(pending);
    vi.mocked(api.reissueInvoice).mockResolvedValue({...issued,version:4,effective_revision:2});
    show(<InvoiceFormPage/>,'/invoices/i1/edit?mode=revision');const user=userEvent.setup();await screen.findByDisplayValue('Consultancy');
    expect(screen.getByLabelText('Invoice number')).toHaveValue('INV-000001');expect(screen.getByLabelText('Invoice number')).toHaveAttribute('readonly');
    await user.click(screen.getByRole('button',{name:'Save Revision Proposal'}));expect(api.requestRevision).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText('Correction reason'),'Correct amount');
    await user.click(screen.getByRole('button',{name:'Save Revision Proposal'}));
    expect(await screen.findByRole('status')).toHaveTextContent('Pending accounting-owner approval');
    expect(api.requestRevision).toHaveBeenCalledWith('i1',expect.objectContaining({version:2}),'Correct amount');
    expect(api.saveInvoice).not.toHaveBeenCalled();expect(api.replacementInvoice).not.toHaveBeenCalled();
    expect(screen.getByRole('button',{name:'Approve & Reissue Saved Revision'})).toBeDisabled();
    await user.type(screen.getByLabelText('Accounting approval reason'),'Owner reviewed');
    await user.click(screen.getByRole('button',{name:'Approve & Reissue Saved Revision'}));
    await waitFor(()=>expect(api.reissueInvoice).toHaveBeenCalledWith('i1',3,'proposal-1','Owner reviewed'));
  });
  it('shows historical and current revisions with explicit historical PDF downloads',async()=>{
    vi.mocked(api.getInvoice).mockResolvedValue({...issued,effective_revision:2});
    vi.mocked(api.getInvoiceRevisions).mockResolvedValue([{revision_number:1,previous_revision:null,current:false,status:'issued',reason:'Original'},{revision_number:2,previous_revision:1,current:true,status:'issued',reason:'Corrected'}]);
    show(<InvoiceViewPage/>,'/invoices/i1');const user=userEvent.setup();await screen.findByText(/Revision 1 \(historical\)/);
    expect(screen.getByText(/Revision 2 \(current effective revision\)/)).toBeInTheDocument();
    await user.click(screen.getByRole('button',{name:'Download revision 1 PDF'}));expect(api.historicalInvoicePdf).toHaveBeenCalledWith('i1',1);
  });
  it('uses controlled owner archive for issued Delete and requires a reason',async()=>{
    vi.mocked(api.getInvoice).mockResolvedValue(issued);
    vi.mocked(api.deleteIssuedInvoice).mockResolvedValue({...issued,is_archived:true});
    show(<InvoiceViewPage/>,'/invoices/i1');const user=userEvent.setup();await screen.findByTitle('Invoice PDF');
    await user.click(screen.getByRole('button',{name:'Delete'}));
    expect(screen.getByRole('button',{name:'Approve Archive of Issued Invoice'})).toBeDisabled();
    await user.type(screen.getByLabelText('Deletion / archive reason'),'Owner archive approval');
    await user.click(screen.getByRole('button',{name:'Approve Archive of Issued Invoice'}));
    expect(api.deleteIssuedInvoice).toHaveBeenCalledWith('i1',2,'Owner archive approval');expect(api.deleteInvoice).not.toHaveBeenCalled();
  });
});


it('prints only the freshly fetched current PDF',async()=>{
  const oldPdf=new Blob(['old']),freshPdf=new Blob(['fresh']);
  vi.mocked(api.invoicePdf).mockImplementation(async(_id,purpose)=>purpose==='print'?freshPdf:oldPdf);
  vi.mocked(URL.createObjectURL).mockImplementation(blob=>blob===freshPdf?'blob:fresh':'blob:original');
  show(<InvoiceViewPage/>,'/invoices/i1');const user=userEvent.setup();
  expect(await screen.findByTitle('Invoice PDF')).toHaveAttribute('src','blob:original');
  await user.click(screen.getByRole('button',{name:'Print'}));
  const printFrame=await screen.findByTitle('Print latest invoice') as HTMLIFrameElement;
  expect(printFrame).toHaveAttribute('src','blob:fresh');
  vi.spyOn(printFrame.contentWindow!,'focus').mockImplementation(()=>{});
  const print=vi.spyOn(printFrame.contentWindow!,'print').mockImplementation(()=>{});
  fireEvent.load(printFrame);expect(print).toHaveBeenCalledTimes(1);
  expect(api.invoicePdf).toHaveBeenCalledWith('i1','print');
});
