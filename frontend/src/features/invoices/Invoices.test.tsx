import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";
import { InvoiceListPage } from "./InvoiceListPage";
import { InvoiceFormPage } from "./InvoiceFormPage";
import { InvoiceViewPage } from "./InvoiceViewPage";
import { InvoiceSettingsPage } from "./InvoiceSettingsPage";

const permissions=vi.hoisted(()=>({create:true,edit:true}));
vi.mock("@/features/access_control/usePermissions",()=>({usePermissions:()=>({can:(_key: string,action: string)=>action==="view"||permissions[action as "create"|"edit"]})}));
vi.mock("./api",async original=>({...await original<typeof import("./api")>(),listInvoices:vi.fn(),getDefaults:vi.fn(),getCustomers:vi.fn(),saveInvoice:vi.fn(),previewPdf:vi.fn(),getInvoice:vi.fn(),invoicePdf:vi.fn(),setInvoiceStatus:vi.fn(),duplicateInvoice:vi.fn(),getSettings:vi.fn(),saveSettings:vi.fn(),uploadSignature:vi.fn(),downloadPdf:vi.fn()}));
const fixture={id:"i1",invoice_number:"INV-000001",customer_id:null,customer:{name:"Acme",address:"Street",city:"Pune",state:"Maharashtra",pincode:"411030",country:"India",gstin:"",phone:"",email:""},invoice_date:"2026-10-04",due_date:"2026-10-04",place_of_supply:"",terms:"",tax_type:"IGST" as const,version:1,status:"draft" as const,items:[{description:"Consultancy",hsn:"9971",quantity:"3",unit:"nos.s",rate:"7753.71",gst_rate:"18"}],subtotal:"23261.13",gst_total:"4187.00",grand_total:"27448.13",amount_in_words:"Words",created_by_name:"Owner",created_at:"2026-10-04T00:00:00Z"};
beforeEach(()=>{
  vi.clearAllMocks();permissions.create=true;permissions.edit=true;
  vi.stubGlobal("URL",Object.assign(URL,{createObjectURL:vi.fn(()=>"blob:invoice"),revokeObjectURL:vi.fn()}));
  vi.mocked(api.listInvoices).mockResolvedValue({items:[fixture],total:1,total_pages:1});
  vi.mocked(api.getDefaults).mockResolvedValue({default_gst:"18",default_terms:"",bank_name:"Bank"} as api.Company);
  vi.mocked(api.getCustomers).mockResolvedValue([]);vi.mocked(api.getInvoice).mockResolvedValue(fixture);
  vi.mocked(api.invoicePdf).mockResolvedValue(new Blob(["pdf"]));vi.mocked(api.previewPdf).mockResolvedValue(new Blob(["preview"]));
  vi.mocked(api.saveInvoice).mockResolvedValue(fixture);
});
function show(element: React.ReactNode,path="/") {render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/" element={element}/><Route path="/invoices/:invoiceId/edit" element={element}/><Route path="/invoices/:invoiceId" element={path==="/"?<p>Saved invoice</p>:element}/></Routes></MemoryRouter>);}
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
    expect(screen.queryByText("Edit")).not.toBeInTheDocument();expect(screen.queryByText("Issue invoice")).not.toBeInTheDocument();
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
