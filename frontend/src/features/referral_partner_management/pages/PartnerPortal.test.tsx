import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ReferralPartnerListPage } from "./ReferralPartnerListPage";
import { uploadPartnerDocument } from "./partnerDocuments";
import { PartnerKycPage, type KycField } from "./PartnerKycPage";
import { CustomerPartnerReferralPage } from "./PartnerReferralsPage";
import { CommissionLedgerPage } from "./CommissionLedgerPage";
import { PartnerPayments } from "./PartnerPayments";
import { PartnerReportsPage } from "./PartnerReportsPage";
import { CommissionHistoryDialog } from "../components/CommissionHistoryDialog";
import { ReferralPartnersLayout } from "./ReferralPartnersLayout";

const mocks=vi.hoisted(()=>({request:vi.fn(),raw:vi.fn(),role:"customer",isOwner:true}));
vi.mock("@/shared/api/client",async original=>({...await original<typeof import("@/shared/api/client")>(),apiRequest:mocks.request,apiRequestRaw:mocks.raw,getAccessToken:()=>"synthetic-test-token"}));
vi.mock("@/features/access_control/usePermissions",()=>({usePermissions:()=>({isOwner:mocks.isOwner,loading:false,can:()=>true})}));
vi.mock("@/components/layout/useNavKeys",()=>({useNavKeys:()=>new Set(["referral_partners","commission_rules","commission_ledger"])}));
vi.mock("@/features/auth/useAuth",()=>({useAuth:()=>({role:mocks.role})}));
const field=(key:string,kind="text",condition_key:string|null=null,condition_value:string|null=null):KycField=>({key,label:key,kind,required:true,hidden:false,help_text:"",options:key==="house_type"?["own","rented"]:[],condition_key,condition_value,max_length:100,max_size_mb:5,mime_types:["application/pdf","image/png"]});
const state=()=>({partner:{id:"partner-a",full_name:"Synthetic Partner",mobile:"9000000011",email:null,kyc_status:"pending",account_active:true,submission_mode:"partner_review",version:1},submission:null,values:{house_type:"own"},documents:[],configuration:{version:3,fields:[field("house_type","dropdown"),field("own_house_proof","file","house_type","own"),field("rental_agreement","file","house_type","rented")],aadhaar_format:"either",required_agreement_ids:[],retention_days:365}});
function mount(child:React.ReactNode,path="/"){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter initialEntries={[path]}>{child}</MemoryRouter></QueryClientProvider>);}
beforeEach(()=>{vi.clearAllMocks();sessionStorage.clear();mocks.role="customer";mocks.isOwner=true;mocks.raw.mockResolvedValue({data:[],meta:{pagination:{total:0}}});mocks.request.mockResolvedValue(state());});

it("creates a password Partner account with a stable request key and no invitation",async()=>{
  mount(<ReferralPartnerListPage/>);
  fireEvent.click(screen.getByRole("button",{name:/Create Partner Account/}));
  const dialog=screen.getByRole("dialog",{name:"Create Partner Account"});
  fireEvent.change(within(dialog).getByLabelText("Full Name"),{target:{value:"Synthetic Partner"}});
  fireEvent.change(within(dialog).getByLabelText("Mobile"),{target:{value:"9000000011"}});
  fireEvent.change(within(dialog).getByLabelText("Initial Password"),{target:{value:"SyntheticPass1!"}});
  fireEvent.change(within(dialog).getByLabelText("Confirm Password"),{target:{value:"SyntheticPass1!"}});
  fireEvent.click(within(dialog).getByRole("button",{name:"Show passwords"}));
  expect(within(dialog).getByLabelText("Initial Password")).toHaveAttribute("type","text");
  fireEvent.click(within(dialog).getByRole("button",{name:"Create Account"}));
  await waitFor(()=>expect(mocks.request).toHaveBeenCalledWith("/referral-partners",expect.objectContaining({method:"POST"})));
  const payload=JSON.parse(mocks.request.mock.calls.find(([url])=>url==="/referral-partners")![1].body);
  expect(payload.initial_password).toBe("SyntheticPass1!");expect(payload.confirm_password).toBe(payload.initial_password);expect(payload.request_id.length).toBeGreaterThan(15);
  expect(mocks.request.mock.calls.some(([url])=>String(url).includes("otp"))).toBe(false);
});

it("renders conditional KYC proof fields using the published form",async()=>{
  mount(<PartnerKycPage/>);
  expect(await screen.findByLabelText("own_house_proof file")).toBeInTheDocument();
  expect(screen.queryByLabelText("rental_agreement file")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("house_type"),{target:{value:"rented"}});
  expect(screen.getByLabelText("rental_agreement file")).toBeInTheDocument();
  expect(screen.queryByLabelText("own_house_proof file")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"Save KYC draft"}));
  await waitFor(()=>expect(mocks.request.mock.calls.some(([url,options])=>url==="/partner-portal/kyc"&&options?.method==="PUT")).toBe(true));
  const payload=JSON.parse(mocks.request.mock.calls.find(([,options])=>options?.method==="PUT")![1].body);
  expect(payload.form_version).toBe(3);expect(payload.values.house_type).toBe("rented");expect(payload).not.toHaveProperty("mobile");
});

it("locks submitted KYC and preserves review state",async()=>{
  const submitted={...state(),submission:{version:2,status:"submitted",form_version:3,consent:true,accepted_agreement_ids:[]}};
  mocks.request.mockResolvedValue(submitted);
  mount(<PartnerKycPage/>);
  expect(await screen.findByLabelText("house_type")).toBeDisabled();
  expect(screen.queryByRole("button",{name:"Save KYC draft"})).not.toBeInTheDocument();
});

it("uses private SSE upload headers and sends a PDF password only to confirmation",async()=>{
  const transport=vi.fn().mockResolvedValue({ok:true});vi.stubGlobal("fetch",transport);
  mocks.request.mockResolvedValueOnce({ticket:"synthetic-private-ticket",upload_url:"https://synthetic-storage.invalid/private",upload_headers:{"x-amz-server-side-encryption":"AES256"}}).mockResolvedValueOnce({id:"document"});
  await uploadPartnerDocument(new File(["synthetic"],"masked.pdf",{type:"application/pdf"}),"aadhaar","file","SyntheticPdfPassword");
  expect(transport).toHaveBeenCalledWith("https://synthetic-storage.invalid/private",expect.objectContaining({headers:{"Content-Type":"application/pdf","x-amz-server-side-encryption":"AES256"}}));
  const ticketBody=JSON.parse(mocks.request.mock.calls[0][1].body);expect(ticketBody).not.toHaveProperty("pdf_password");
  expect(JSON.parse(mocks.request.mock.calls[1][1].body).pdf_password).toBe("SyntheticPdfPassword");
  vi.unstubAllGlobals();
});

it("preserves the referral fragment through the existing Customer login return",async()=>{
  mocks.role="";
  const token="x".repeat(43);
  mount(<Routes><Route path="/partner-referral" element={<CustomerPartnerReferralPage/>}/></Routes>,`/partner-referral#${token}`);
  expect(screen.getByRole("link",{name:"Customer login"})).toHaveAttribute("href","/login?return=%2Fpartner-referral");
  await waitFor(()=>expect(sessionStorage.getItem("afs_partner_referral_token")).toBe(token));
  expect(screen.getByRole("link",{name:"Create Customer account"})).toHaveAttribute("href","/register?return=%2Fpartner-referral");
});

afterEach(()=>vi.unstubAllGlobals());

it("preserves unsaved KYC answers when a private upload refreshes document history",async()=>{
  const initial={...state(),configuration:{...state().configuration,fields:[field("account_holder"),field("bank_passbook","file")]}};
  mocks.request.mockImplementation(async(url:string,options?:RequestInit)=>{
    if(url==="/partner-portal/kyc/uploads")return {ticket:"synthetic-ticket",upload_url:"https://synthetic-storage.invalid/upload"};
    if(url==="/partner-portal/kyc/uploads/confirm")return {id:"synthetic-document"};
    if(options?.method==="PUT")return initial;
    return initial;
  });
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true}));
  mount(<PartnerKycPage/>);
  fireEvent.change(await screen.findByLabelText("account_holder"),{target:{value:"Unsaved synthetic holder"}});
  fireEvent.change(screen.getByLabelText("bank_passbook file"),{target:{files:[new File(["synthetic PDF"],"passbook.pdf",{type:"application/pdf"})]}});
  await screen.findByText("Document uploaded for review.");
  expect(screen.getByLabelText("account_holder")).toHaveValue("Unsaved synthetic holder");
  fireEvent.click(screen.getByRole("button",{name:"Save KYC draft"}));
  await waitFor(()=>expect(mocks.request.mock.calls.some(([,options])=>options?.method==="PUT")).toBe(true));
  const body=JSON.parse(mocks.request.mock.calls.find(([,options])=>options?.method==="PUT")![1].body);
  expect(body.values.account_holder).toBe("Unsaved synthetic holder");
});

it("requires saving changed KYC answers before submitting the saved draft",async()=>{
  mocks.request.mockResolvedValue({...state(),submission:{version:1,status:"draft",consent:false,accepted_agreement_ids:[]},configuration:{...state().configuration,fields:[field("account_holder")]}});
  mount(<PartnerKycPage/>);
  const holder=await screen.findByLabelText("account_holder");
  expect(screen.getByRole("button",{name:"Submit saved KYC"})).toBeEnabled();
  fireEvent.change(holder,{target:{value:"Unsaved edit"}});
  expect(screen.getByRole("button",{name:"Submit saved KYC"})).toBeDisabled();
  expect(screen.getByText("Save your changes before submitting KYC for review.")).toBeInTheDocument();
});

it("reserves only the selected approved balance after existing reservations",async()=>{
  mocks.raw.mockImplementation(async(url:string)=>({data:url.startsWith("/commission-entries")?[{id:"entry-a",partner_id:"partner-a",partner_name:"Synthetic Partner",case_id:"case-a",case_type:"loan",commission_amount:100,total_earned_amount:150,base_amount:5000,status:"approved",outstanding_amount:120.3,reserved_amount:20.1,paid_amount:29.7,version:1}]:[],meta:{pagination:{total:url.startsWith("/commission-entries")?1:0}}}));
  mount(<CommissionLedgerPage/>);
  fireEvent.click(await screen.findByRole("checkbox",{name:"Select commission entry-a"}));
  fireEvent.click(screen.getByRole("button",{name:"Reserve selected balances"}));
  await waitFor(()=>expect(mocks.request).toHaveBeenCalledWith("/partner-management/payments",expect.objectContaining({method:"POST"})));
  const body=JSON.parse(mocks.request.mock.calls.find(([url])=>url==="/partner-management/payments")![1].body);
  expect(body.allocations).toEqual([{entry_id:"entry-a",amount:100.2}]);
  expect(body.request_id.length).toBeGreaterThan(15);
});

it("does not confirm a reserved payment without actual-payment acknowledgement",async()=>{
  mocks.raw.mockImplementation(async(url:string)=>({data:url.includes("/payments")?[{id:"payment-a",partner_id:"partner-a",amount:100,status:"initiated",allocations:[{entry_id:"entry-a",amount:100}]}]:[],meta:{pagination:{total:1}}}));
  mount(<PartnerPayments revision={0} onChanged={vi.fn()}/>);
  fireEvent.click(await screen.findByRole("button",{name:"Confirm actual payment"}));
  const dialog=screen.getByRole("dialog");
  expect(within(dialog).getByRole("button",{name:"Save"})).toBeDisabled();
  fireEvent.change(within(dialog).getByLabelText("Payment reference"),{target:{value:"SYNTHETIC-REFERENCE"}});
  fireEvent.click(within(dialog).getByRole("checkbox"));
  fireEvent.click(within(dialog).getByRole("button",{name:"Save"}));
  await waitFor(()=>expect(mocks.request).toHaveBeenCalledWith("/partner-management/payments/payment-a/confirm",expect.objectContaining({method:"POST"})));
  const body=JSON.parse(mocks.request.mock.calls.find(([url])=>url.endsWith("/confirm"))![1].body);
  expect(body.confirmed).toBe(true);expect(body.payment_reference).toBe("SYNTHETIC-REFERENCE");
});

it("loads searchable Owner report Partner options within the API page-size limit",async()=>{
  mocks.raw.mockImplementation(async(url:string)=>{
    if(url.includes("page_size=200"))throw new Error("Invalid page size");
    return {data:url.startsWith("/referral-partners")?[{id:"partner-a",full_name:"Synthetic Available Partner"}]:[],meta:{pagination:{total:1}}};
  });
  mocks.request.mockImplementation(async(url:string)=>url==="/loan-products"?[{id:"product-a",name:"Synthetic Loan"}]:{columns:[],rows:[]});
  mount(<PartnerReportsPage/>);
  expect(await screen.findByRole("option",{name:"Synthetic Available Partner"})).toBeInTheDocument();
  expect(screen.getByRole("option",{name:"Synthetic Loan"})).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Search report Partners"),{target:{value:"Available"}});
  await waitFor(()=>expect(mocks.raw.mock.calls.some(([url])=>url.includes("page_size=100")&&url.includes("search=Available"))).toBe(true));
});

it("shows immutable original and later-tranche commission rates separately",async()=>{
  mocks.raw.mockResolvedValue({data:{original:{kind:"original_earning",amount:1000,base_amount:50000,rate_or_amount:2,calculation_type:"percentage",rule_version:1},events:[{id:"event-a",kind:"disbursement_earning",amount:900,base_amount:30000,rate_or_amount:3,calculation_type:"percentage",rule_version:2}]},meta:{pagination:{total:1}}});
  mount(<CommissionHistoryDialog entryId="entry-a" onClose={vi.fn()}/>);
  expect(await screen.findByRole("cell",{name:"2%"})).toBeInTheDocument();
  expect(screen.getByRole("cell",{name:"3%"})).toBeInTheDocument();
  expect(screen.getByText("original earning")).toBeInTheDocument();
  expect(screen.getByText("disbursement earning")).toBeInTheDocument();
  expect(mocks.raw).toHaveBeenCalledWith("/commission-entries/entry-a/history?page=1&page_size=20");
});

it("exposes Owner KYC and report tabs through the existing Partner navigation key",()=>{
  mount(<ReferralPartnersLayout/>,"/referral-partners/reports");
  expect(screen.getByRole("link",{name:"KYC Review"})).toBeInTheDocument();
  expect(screen.getByRole("link",{name:"KYC Configuration"})).toBeInTheDocument();
  expect(screen.getByRole("link",{name:"Referral Reports"})).toHaveAttribute("aria-current","page");
  expect(screen.getByRole("link",{name:"Partners"})).not.toHaveAttribute("aria-current");
});

it("keeps Employee Partner navigation limited to the existing Partners list",()=>{
  mocks.isOwner=false;mount(<ReferralPartnersLayout/>);
  expect(screen.getByRole("link",{name:"Partners"})).toBeInTheDocument();
  expect(screen.queryByRole("link",{name:"KYC Review"})).not.toBeInTheDocument();
  expect(screen.queryByRole("link",{name:"Referral Reports"})).not.toBeInTheDocument();
});
