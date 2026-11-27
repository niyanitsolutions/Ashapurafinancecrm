import {render,screen,fireEvent,waitFor} from "@testing-library/react";
import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {MemoryRouter} from "react-router-dom";
import {beforeEach,expect,it,vi} from "vitest";
import {MoveApplicationToLoanManagementModal} from "./MoveApplicationToLoanManagementModal";
const request=vi.hoisted(()=>vi.fn());
vi.mock("@/shared/api/client",()=>({apiRequest:request}));
vi.mock("@/features/auth/useAuth",()=>({useAuth:()=>({userId:"synthetic-owner"})}));
vi.mock("@/features/access_control/usePermissions",()=>({usePermissions:()=>({can:()=>true})}));
beforeEach(()=>{request.mockReset();request.mockResolvedValue({movement_status:"Not moved"});});
function mount(onChanged=vi.fn(),onClose=vi.fn()){render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter><MoveApplicationToLoanManagementModal lead={{application_id:"app-1",lead_code:"SYNTHETIC-APP"}} onChanged={onChanged} onClose={onClose}/></MemoryRouter></QueryClientProvider>);}
it("allows Daily movement without a document verification gate",async()=>{mount();expect(await screen.findByRole("button",{name:"Move to Daily Follow-up"})).toBeEnabled();expect(screen.getByText(/Document verification is preserved/)).toBeInTheDocument();expect(request.mock.calls.some(([url])=>url.includes("move-to-loan-management"))).toBe(false);});
it("uses the shared movement endpoint and refreshes/closes on success",async()=>{const changed=vi.fn(),close=vi.fn();mount(changed,close);fireEvent.click(await screen.findByRole("button",{name:"Move to Daily Follow-up"}));await waitFor(()=>expect(changed).toHaveBeenCalledOnce());expect(close).toHaveBeenCalledOnce();expect(request).toHaveBeenCalledWith("/daily-operations/applications/app-1/move",{method:"POST"});});
it("retains the form and displays movement failure",async()=>{request.mockImplementation((_url:string,options?:{method:string})=>options?.method==="POST"?Promise.reject(new Error("Assignment changed")):Promise.resolve({movement_status:"Not moved"}));const changed=vi.fn();mount(changed);fireEvent.click(await screen.findByRole("button",{name:"Move to Daily Follow-up"}));expect(await screen.findByRole("alert")).toHaveTextContent("Assignment changed");expect(changed).not.toHaveBeenCalled();});
