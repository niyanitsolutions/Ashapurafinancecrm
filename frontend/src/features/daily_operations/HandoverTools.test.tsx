import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {MemoryRouter} from "react-router-dom";
import {beforeEach,expect,it,vi} from "vitest";
import {TransferScope,TransferCheck,TransferTag} from "./HandoverTools";
import {MoveToDailyFollowUp} from "./MoveToDailyFollowUp";
const mocks=vi.hoisted(()=>({request:vi.fn()}));
vi.mock("@/shared/api/client",()=>({apiRequest:mocks.request}));
vi.mock("@/features/auth/useAuth",()=>({useAuth:()=>({userId:"synthetic-owner"})}));
vi.mock("@/features/access_control/usePermissions",()=>({usePermissions:()=>({can:()=>true})}));
const provider=(child:React.ReactNode)=>render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter>{child}</MemoryRouter></QueryClientProvider>);
beforeEach(()=>{mocks.request.mockReset();});
it("transfers exactly the selected versioned records with a durable request key",async()=>{
 mocks.request.mockImplementation((url:string)=>Promise.resolve(url.endsWith("/context")?{items:[{id:"a",version:3,assigned_to:"sender"},{id:"b",version:7,assigned_to:"sender"}]}:url.endsWith("/receivers")?{items:[{id:"receiver",name:"Synthetic Receiver"}]}:{bulk_reference:"synthetic-bulk"}));
 const done=vi.fn();provider(<TransferScope collection="applications" ids={["a","b"]} allowed onTransferred={done}><TransferCheck id="a"/><TransferCheck id="b"/></TransferScope>);
 fireEvent.click(await screen.findByRole("checkbox",{name:"Select b for transfer"}));fireEvent.click(screen.getByRole("button",{name:"Transfer Selected"}));
 await screen.findByRole("option",{name:"Synthetic Receiver"});fireEvent.change(screen.getByLabelText("Receiving employee"),{target:{value:"receiver"}});fireEvent.click(screen.getByRole("button",{name:"Confirm transfer"}));
 await waitFor(()=>expect(done).toHaveBeenCalledOnce());const call=mocks.request.mock.calls.find(([url])=>url==="/daily-operations/handovers");const body=JSON.parse(call![1].body);expect(body.records).toEqual([{collection:"applications",id:"b",version:7}]);expect(body.employee_id).toBe("receiver");expect(body.request_id.length).toBeGreaterThan(15);
});
it("retains selection and remarks after a rejected transfer and does not auto retry",async()=>{
 mocks.request.mockImplementation((url:string)=>url.endsWith("/context")?Promise.resolve({items:[{id:"a",version:1,assigned_to:"sender"}]}):url.endsWith("/receivers")?Promise.resolve({items:[{id:"r",name:"Receiver"}]}):Promise.reject(new Error("Ownership changed. Nothing was transferred.")));
 provider(<TransferScope collection="leads" ids={["a"]} allowed onTransferred={vi.fn()}><TransferCheck id="a"/></TransferScope>);fireEvent.click(await screen.findByRole("checkbox",{name:"Select a for transfer"}));fireEvent.click(screen.getByRole("button",{name:"Transfer Selected"}));await screen.findByRole("option",{name:"Receiver"});fireEvent.change(screen.getByLabelText("Receiving employee"),{target:{value:"r"}});fireEvent.change(screen.getByLabelText("Transfer remarks (optional)"),{target:{value:"Keep this handover note"}});fireEvent.click(screen.getByRole("button",{name:"Confirm transfer"}));await screen.findAllByText("Ownership changed. Nothing was transferred.");expect(screen.getByLabelText("Transfer remarks (optional)")).toHaveValue("Keep this handover note");expect(mocks.request.mock.calls.filter(([url])=>url==="/daily-operations/handovers")).toHaveLength(1);
});
it("shows current transfer context without granting transfer actions",async()=>{
 mocks.request.mockResolvedValue({items:[{id:"a",version:1,assigned_to:"receiver",assigned_to_name:"Receiver",transfer:{from_employee_id:"sender",from_employee_name:"Sender",to_employee_id:"receiver",to_employee_name:"Receiver"}}]});provider(<TransferScope collection="leads" ids={["a"]} allowed={false} onTransferred={vi.fn()}><TransferTag id="a"/></TransferScope>);expect(await screen.findByText("Transferred By: Sender")).toBeInTheDocument();expect(screen.getByText("Current Owner: Receiver")).toBeInTheDocument();expect(screen.queryByRole("button",{name:"Transfer Selected"})).not.toBeInTheDocument();
});
it("moves without a document gate and reports the existing workspace",async()=>{
 let moved=false;mocks.request.mockImplementation((_url:string,options?:{method:string})=>{if(options?.method==="POST"){moved=true;return Promise.resolve({id:"w"});}return Promise.resolve(moved?{id:"w",movement_status:"Moved to Daily Follow-up"}:{movement_status:"Not moved"});});provider(<MoveToDailyFollowUp applicationId="app"/>);fireEvent.click(await screen.findByRole("button",{name:"Move to Daily Follow-up"}));expect(await screen.findByRole("link",{name:"Open Daily Follow-up"})).toHaveAttribute("href","/daily-operations/follow-ups?record=w");expect(mocks.request.mock.calls.filter(([,options])=>options?.method==="POST")).toHaveLength(1);
});
it("retains the movement action and shows a server failure",async()=>{
 mocks.request.mockImplementation((_url:string,options?:{method:string})=>options?.method==="POST"?Promise.reject(new Error("Source assignment changed")):Promise.resolve({movement_status:"Not moved"}));provider(<MoveToDailyFollowUp applicationId="app"/>);fireEvent.click(await screen.findByRole("button",{name:"Move to Daily Follow-up"}));expect(await screen.findByRole("alert")).toHaveTextContent("Source assignment changed");expect(screen.getByRole("button",{name:"Move to Daily Follow-up"})).toBeEnabled();
});
