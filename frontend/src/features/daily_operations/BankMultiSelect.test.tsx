import { useState } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import {LoanTypeField} from "./LoanTypeField";
import { BankMultiSelect } from "./BankMultiSelect";
import { RecordForm } from "./RecordForm";
import { DailyOperationsPage } from "./DailyOperationsPage";
import type { BankSelection } from "./bankOptions";
const mocks=vi.hoisted(()=>({request:vi.fn(),save:vi.fn(),lookups:vi.fn(),list:vi.fn(),download:vi.fn(),manage:true}));
vi.mock("@/features/auth/useAuth",()=>({useAuth:()=>({userId:"employee-a"})}));
vi.mock("@/features/access_control/usePermissions",()=>({usePermissions:()=>({can:()=>mocks.manage,isOwner:false,loading:false})}));
vi.mock("@/shared/api/client",()=>({apiRequest:mocks.request}));
vi.mock("./api",async original=>({...await original<typeof import("./api")>(),getLookups:mocks.lookups,saveRecord:mocks.save,listRecords:mocks.list,download:mocks.download}));
const bank={id:"aaaaaaaaaaaaaaaaaaaaaaaa",name:"WERIZE FINANCE",version:1,is_active:true};
let rows:typeof bank[];
function wrap(child:React.ReactNode){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter>{child}</MemoryRouter></QueryClientProvider>);}
function Selector({initial=[]}:{initial?:BankSelection[]}){const [value,setValue]=useState(initial);return <BankMultiSelect value={value} onChange={setValue}/>;}
async function open(){fireEvent.click(screen.getByLabelText("Bank / NBFC"));await screen.findByRole("checkbox",{name:bank.name});}
beforeEach(()=>{vi.clearAllMocks();mocks.manage=true;rows=[{...bank},{...bank,id:"bbbbbbbbbbbbbbbbbbbbbbbb",name:"FINNABLE FINANCE"}];mocks.request.mockImplementation(async(path:string,init?:RequestInit)=>{if(path.includes("follow-up-status-options"))return ["FOLLOW UP PENDING","NEXT FOLLOW UP","DISBURSE","REJECTED WITH REASON","CASE ON HOLD WITH REASON","Re-Eligible"].map((name,index)=>({id:String(index),name,value:name,is_active:true,color:"#D9F5E3"}));if(!init)return rows;const body=JSON.parse(String(init.body));if(path.endsWith("bank-options")){const added={...bank,id:"cccccccccccccccccccccccc",name:body.name};rows=[...rows,added];return added;}rows=rows.map(r=>r.id===bank.id?{...r,...(body.name?{name:body.name}:{}),is_active:!path.endsWith("/archive"),version:r.version+1}:r);return rows[0];});mocks.lookups.mockResolvedValue({self_id:"employee-a",self_name:"Employee A",employees:[],leads:[],cases:[]});mocks.save.mockResolvedValue({id:"record"});mocks.list.mockResolvedValue({items:[],total:0});});
it("selects multiple banks as chips and removes one independently",async()=>{wrap(<Selector/>);await open();fireEvent.click(screen.getByRole("checkbox",{name:bank.name}));fireEvent.click(screen.getByRole("checkbox",{name:"FINNABLE FINANCE"}));expect(within(screen.getByLabelText("Selected banks")).getByText(bank.name)).toBeVisible();fireEvent.click(screen.getByRole("button",{name:`Remove selected bank ${bank.name}`}));expect(screen.getByRole("checkbox",{name:bank.name})).not.toBeChecked();expect(screen.getByRole("checkbox",{name:"FINNABLE FINANCE"})).toBeChecked();});
it("searches and shows a useful no-match state",async()=>{wrap(<Selector/>);await open();fireEvent.change(screen.getByLabelText("Search banks / NBFCs"),{target:{value:"missing"}});expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();expect(screen.getByText(/No matching banks/)).toBeVisible();});
it("creates a custom option and selects it immediately",async()=>{wrap(<Selector/>);await open();fireEvent.click(screen.getByRole("button",{name:"Add Custom Bank / NBFC"}));fireEvent.change(screen.getByLabelText("Bank / NBFC name"),{target:{value:"INCRED FINANCE"}});fireEvent.click(screen.getByRole("button",{name:"Save bank option"}));expect(await screen.findByRole("button",{name:"Remove selected bank INCRED FINANCE"})).toBeVisible();});
it("renames, confirms archival and restores options",async()=>{wrap(<Selector/>);await open();fireEvent.click(screen.getByRole("button",{name:"Manage Bank Options"}));fireEvent.click(screen.getByRole("button",{name:`Edit ${bank.name}`}));fireEvent.change(screen.getByLabelText("Bank / NBFC name"),{target:{value:"Updated bank"}});fireEvent.click(screen.getByRole("button",{name:"Save bank option"}));fireEvent.click(await screen.findByRole("button",{name:"Archive Updated bank"}));expect(rows[0].is_active).toBe(true);fireEvent.click(within(screen.getByRole("dialog")).getByRole("button",{name:"Archive bank"}));fireEvent.click(await screen.findByRole("button",{name:"Restore Updated bank"}));await screen.findByRole("button",{name:"Archive Updated bank"});});
it("keeps errors and typed values after a duplicate conflict",async()=>{wrap(<Selector/>);await open();fireEvent.click(screen.getByRole("button",{name:"Add Custom Bank / NBFC"}));fireEvent.change(screen.getByLabelText("Bank / NBFC name"),{target:{value:"Duplicate"}});mocks.request.mockImplementation(async(_path:string,init?:RequestInit)=>{if(init)throw new Error("Already exists");return rows;});fireEvent.click(screen.getByRole("button",{name:"Save bank option"}));expect(await screen.findByRole("alert")).toHaveTextContent("Already exists");expect(screen.getByLabelText("Bank / NBFC name")).toHaveValue("Duplicate");});
it("retains historical archived and legacy chips",async()=>{rows[0].is_active=false;wrap(<Selector initial={[{option_id:bank.id,name:"Old name"},{option_id:null,name:"Legacy name"}]}/>);fireEvent.click(screen.getByLabelText("Bank / NBFC"));await screen.findByRole("checkbox",{name:"FINNABLE FINANCE"});expect(screen.getByRole("button",{name:"Remove selected bank Old name"})).toBeVisible();expect(screen.getByRole("button",{name:"Remove selected bank Legacy name"})).toBeVisible();expect(screen.queryByRole("checkbox",{name:bank.name})).not.toBeInTheDocument();});
it("hides management without permission",async()=>{mocks.manage=false;wrap(<Selector/>);await open();expect(screen.queryByRole("button",{name:"Manage Bank Options"})).not.toBeInTheDocument();});
it.each([false,true])("saves DISBURSE with multiple banks without CRM selection, edit=%s",async(editing)=>{wrap(<RecordForm area="follow-ups" record={editing?{id:"record",version:2,date:"2026-11-12",remarks_date:"2026-11-12",due_date:null,status:"DISBURSE",customer_name:"Customer",customer_number:"9000000000",bank:bank.name,banks:[{option_id:bank.id,name:bank.name}]}:undefined} onSaved={()=>{}} onCancel={()=>{}}/>);await screen.findByRole("option",{name:"DISBURSE"});if(!editing)for(const [label,value]of[["Customer name","Customer"],["Customer number","9000000000"]])fireEvent.change(screen.getByLabelText(label),{target:{value}});fireEvent.change(screen.getByLabelText("Follow-up status"),{target:{value:"DISBURSE"}});await open();if(!editing)fireEvent.click(screen.getByRole("checkbox",{name:bank.name}));fireEvent.click(screen.getByRole("checkbox",{name:"FINNABLE FINANCE"}));expect(screen.queryByLabelText("Verified disbursed loan")).not.toBeInTheDocument();expect(screen.queryByLabelText("Link existing CRM record")).not.toBeInTheDocument();fireEvent.click(screen.getByRole("button",{name:editing?"Save changes":"Save record"}));await waitFor(()=>expect(mocks.save).toHaveBeenCalledWith("follow-ups",expect.objectContaining({status:"DISBURSE",due_date:null,banks:[{option_id:bank.id,name:bank.name},{option_id:"bbbbbbbbbbbbbbbbbbbbbbbb",name:"FINNABLE FINANCE"}]}),editing?"record":undefined));expect(mocks.save.mock.calls[0][1]).not.toHaveProperty("case_id");expect(mocks.save.mock.calls[0][1]).not.toHaveProperty("lead_id");expect(mocks.lookups).toHaveBeenCalledWith("",false);});
it("shows all banks in the table and keeps export available",async()=>{mocks.list.mockResolvedValue({items:[{id:"record",status:"DISBURSE",customer_name:"Customer",bank:"WERIZE FINANCE, FINNABLE FINANCE",banks:[{option_id:bank.id,name:bank.name},{option_id:"bbbbbbbbbbbbbbbbbbbbbbbb",name:"FINNABLE FINANCE"}]}],total:1});wrap(<DailyOperationsPage area="follow-ups"/>);const customer=await screen.findByText("Customer");const row=customer.closest("tr")!;expect(within(row).getByText("WERIZE FINANCE, FINNABLE FINANCE")).toHaveAttribute("title","WERIZE FINANCE, FINNABLE FINANCE");fireEvent.click(screen.getByText("Export",{exact:true}));fireEvent.click(screen.getByRole("button",{name:"CSV"}));expect(mocks.download).toHaveBeenCalled();});

it("reuses option management for a single loan type and allows replacing it",async()=>{
 function Loan(){const [value,setValue]=useState("Historic loan");return <LoanTypeField value={value} onChange={setValue}/>;}
 wrap(<Loan/>);fireEvent.click(screen.getByLabelText("Loan type"));
 await screen.findByRole("checkbox",{name:bank.name});
 fireEvent.click(screen.getByRole("checkbox",{name:bank.name}));
 fireEvent.click(screen.getByRole("checkbox",{name:"FINNABLE FINANCE"}));
 expect(screen.getByRole("checkbox",{name:bank.name})).not.toBeChecked();
 expect(screen.getByRole("checkbox",{name:"FINNABLE FINANCE"})).toBeChecked();
 expect(within(screen.getByLabelText("Selected loan type")).getByText("FINNABLE FINANCE")).toBeVisible();
 expect(screen.getByRole("button",{name:"Manage Loan Types"})).toBeVisible();
 expect(mocks.request).toHaveBeenCalledWith("/daily-operations/loan-type-options?include_archived=true");
});
it("requests default 200 follow-ups and preserves filters when changing page size",async()=>{
 mocks.list.mockResolvedValue({items:[{id:"one",customer_name:"One",status:"FOLLOW UP PENDING"}],total:205});
 wrap(<DailyOperationsPage area="follow-ups"/>);
 await screen.findByText("One");
 expect(mocks.list.mock.calls[0][1]).toContain("page_size=200");
 const size=screen.getByDisplayValue("200 / page");
 expect(within(size).getAllByRole("option").map(row=>row.getAttribute("value"))).toEqual(["20","50","100","150","200"]);
 fireEvent.change(size,{target:{value:"50"}});
 await waitFor(()=>expect(mocks.list.mock.calls.at(-1)?.[1]).toContain("page_size=50"));
});

it.each([false,true])("requires an eligibility date for add/edit without changing dropdown order, edit=%s",async editing=>{
 const record=editing?{id:"record",version:1,status:"Re-Eligible",status_display:"Re-Eligible",customer_name:"Eligible",customer_number:"9000000000",date:"2026-11-15",remarks_date:"2026-11-15",banks:[{option_id:bank.id,name:bank.name}]}:undefined;
 wrap(<RecordForm area="follow-ups" record={record} onSaved={vi.fn()} onCancel={vi.fn()}/>);
 const select=await screen.findByLabelText("Follow-up status");
 await waitFor(()=>expect(within(select).getAllByRole("option").map(option=>option.textContent)).toContain("Re-Eligible"));
 fireEvent.change(select,{target:{value:"Re-Eligible"}});
 expect(screen.getByLabelText("Re-Eligible Date")).toBeRequired();
 expect(screen.queryByLabelText("Next follow-up date")).not.toBeInTheDocument();
 fireEvent.change(screen.getByLabelText("Re-Eligible Date"),{target:{value:"2026-11-20"}});
 fireEvent.change(select,{target:{value:"DISBURSE"}});
 expect(screen.queryByLabelText("Re-Eligible Date")).not.toBeInTheDocument();
 fireEvent.change(select,{target:{value:"Re-Eligible"}});
 expect(screen.getByLabelText("Re-Eligible Date")).toHaveValue("2026-11-20");
 expect(within(select).getAllByRole("option").map(option=>option.textContent).filter(value=>value)).toEqual(expect.arrayContaining(["FOLLOW UP PENDING","NEXT FOLLOW UP","DISBURSE","REJECTED WITH REASON"]));
});
it("uses the selected workflow for list queries and export, and resets pagination",async()=>{
 wrap(<DailyOperationsPage area="follow-ups"/>);
 await screen.findByRole("button",{name:/^Re-Eligible$/});
 fireEvent.click(screen.getByRole("button",{name:/^Re-Eligible$/}));
 await waitFor(()=>expect(mocks.list.mock.calls.at(-1)?.[1]).toContain("workflow=reeligible"));
 expect(screen.getByRole("button",{name:/^Re-Eligible$/})).toHaveAttribute("aria-pressed","true");
 fireEvent.click(screen.getByText("Export",{exact:true}));fireEvent.click(screen.getByRole("button",{name:"CSV"}));
 expect(mocks.download.mock.calls.at(-1)?.[0]).toContain("workflow=reeligible");
 fireEvent.click(screen.getByRole("button",{name:/^Daily Follow-up Data$/}));
 await waitFor(()=>expect(mocks.list.mock.calls.at(-1)?.[1]).toContain("workflow=normal"));
});
