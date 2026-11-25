import { act, render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DocumentCollectionPage } from "./DocumentCollectionPage";
const request = vi.hoisted(() => vi.fn());
vi.mock("@/shared/api/client", () => ({ apiRequest: request }));
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ isOwner: false, can: () => false }) }));
beforeEach(() => { request.mockReset(); });
it("defaults to 200 customer rows, expands applications and applies filters server-side", async () => {
  request.mockImplementation((url: string) => Promise.resolve(url.includes("filter-options") ? {} : url.includes("group_key") ? { items: [{ id: "a1", application_code: "AFS-APP-1", product_name: "Home Loan", status: "submitted" }], total: 1 } : { items: [{ id: "c1", name: "Current Customer", customer_code: "AFS-CUS-1", application_count: 2 }], total: 1 }));
  render(<MemoryRouter><DocumentCollectionPage /></MemoryRouter>);
  await screen.findByText("Current Customer");
  expect(request).toHaveBeenCalledWith(expect.stringContaining("page_size=200"));
  fireEvent.click(screen.getByRole("button", {name:"Expand"}));
  expect(await screen.findByRole("link",{name:"AFS-APP-1"})).toHaveAttribute("href","/applications/a1?from=document-collection&customer_id=c1");
  fireEvent.change(screen.getByRole("searchbox"),{target:{value:"AFS-CUS-1"}});
  fireEvent.click(screen.getByRole("button",{name:"Apply Filters"}));
  await waitFor(() => expect(request).toHaveBeenCalledWith(expect.stringContaining("search=AFS-CUS-1")));
  fireEvent.click(screen.getByRole("button",{name:"Clear Filters"}));
  await waitFor(() => expect(screen.getByRole("searchbox")).toHaveValue(""));
});

function Location(){return <output data-testid="location">{useLocation().search}</output>;}
afterEach(()=>vi.useRealTimers());
const groupRow = {id:"c1",name:"Current Customer",customer_code:"AFS-CUS-1",application_count:2,primary:{id:"a1",application_code:"AFS-APP-1",product_name:"Home Loan",status:"submitted",customer_status:"active",assigned_to_name:"Employee One",created_at:"2026-11-25T00:00:00Z"}};
function fixture(url:string){return url.includes("filter-options")?{assigned_by:[{value:"staff1",label:"Assigning Owner"}],source_id:[{value:"source1",label:"Website"}],follow_up_status:[{value:"custom:status1",label:"Awaiting documents"}]}:url.includes("group_key")?{items:[{...groupRow.primary,customer_name:groupRow.name},{...groupRow.primary,id:"a2",application_code:"AFS-APP-2",product_name:"Personal Loan"}],total:52}:{items:[groupRow],total:600};}
it("renders the reference table, removed filters are absent, and child pages retain independent actions",async()=>{
 request.mockImplementation((url:string)=>Promise.resolve(fixture(url)));render(<MemoryRouter><DocumentCollectionPage/></MemoryRouter>);
 const table=await screen.findByRole("table",{name:"Document Collection customers"});await screen.findByText("Current Customer");
 for(const label of ["Application / Lead Code","Customer Name","Mobile","Source","Product","Assigned To","Application Status","Customer Account Status","Created On","Actions"])expect(within(table).getByRole("columnheader",{name:label})).toBeInTheDocument();
 for(const label of ["Assigned from","Assigned until","Created until","Employee designation"])expect(screen.queryByLabelText(label)).not.toBeInTheDocument();
 fireEvent.click(screen.getByText("Advanced filters"));expect(screen.getByRole("option",{name:"Assigning Owner"})).toHaveValue("staff1");expect(screen.getByRole("option",{name:"Awaiting documents"})).toHaveValue("custom:status1");
 fireEvent.click(screen.getByRole("button",{name:"Expand"}));const region=await screen.findByRole("region",{name:"Applications for Current Customer"});await within(region).findByText("AFS-APP-2");
 expect(within(region).getAllByRole("link",{name:"View"})).toHaveLength(2);fireEvent.click(within(region).getByRole("button",{name:"Next page"}));await waitFor(()=>expect(request).toHaveBeenCalledWith(expect.stringMatching(/group_key=c1.*page=2&page_size=25/)));
 fireEvent.click(screen.getByRole("button",{name:"Collapse"}));expect(screen.queryByRole("region")).not.toBeInTheDocument();
});
it("debounces live search, resets page and URL, drops removed payload fields, and clears without Enter",async()=>{
 vi.useFakeTimers();request.mockImplementation((url:string)=>Promise.resolve(fixture(url)));
 render(<MemoryRouter initialEntries={["/?page=3&assigned_from=2026-01-01&designation_id=old"]}><DocumentCollectionPage/><Location/></MemoryRouter>);await act(async()=>{});
 const input=screen.getByRole("searchbox");fireEvent.change(input,{target:{value:"Current"}});await act(async()=>{await vi.advanceTimersByTimeAsync(150);});fireEvent.change(input,{target:{value:"9000000000"}});await act(async()=>{await vi.advanceTimersByTimeAsync(349);});
 expect(request.mock.calls.filter(([url])=>String(url).includes("search="))).toHaveLength(0);await act(async()=>{await vi.advanceTimersByTimeAsync(2);});
 expect(request).toHaveBeenCalledWith(expect.stringContaining("search=9000000000&page=1"));expect(screen.getByTestId("location")).toHaveTextContent("search=9000000000");
 expect(request.mock.calls.every(([url])=>!String(url).includes("assigned_from")&&!String(url).includes("designation_id"))).toBe(true);
 fireEvent.change(input,{target:{value:""}});await act(async()=>{await vi.advanceTimersByTimeAsync(351);});expect(screen.getByTestId("location")).not.toHaveTextContent("search=");expect(screen.getByRole("searchbox")).toHaveValue("");
});
it("ignores an older request that finishes after the current search",async()=>{
 vi.useFakeTimers();let finishOld!:(value:unknown)=>void;
 request.mockImplementation((url:string)=>url.includes("search=old")?new Promise(resolve=>{finishOld=resolve;}):Promise.resolve(url.includes("search=new")?{items:[{...groupRow,name:"Newest result"}],total:1}:fixture(url)));
 render(<MemoryRouter><DocumentCollectionPage/></MemoryRouter>);await act(async()=>{});fireEvent.change(screen.getByRole("searchbox"),{target:{value:"old"}});await act(async()=>{await vi.advanceTimersByTimeAsync(351);});fireEvent.change(screen.getByRole("searchbox"),{target:{value:"new"}});await act(async()=>{await vi.advanceTimersByTimeAsync(351);});
 expect(screen.getByText("Newest result")).toBeInTheDocument();await act(async()=>{finishOld({items:[{...groupRow,name:"Stale result"}],total:1});});expect(screen.queryByText("Stale result")).not.toBeInTheDocument();expect(screen.getByText("Newest result")).toBeInTheDocument();
});
