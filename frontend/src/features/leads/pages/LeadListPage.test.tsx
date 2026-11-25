import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { LeadListPage } from "./LeadListPage";
const mocks=vi.hoisted(() => ({request:vi.fn(),summary:vi.fn(),move:vi.fn()}));
vi.mock("@/shared/api/client",()=>({apiRequest:mocks.request, apiRequestRaw:vi.fn()}));
vi.mock("@/features/access_control/usePermissions",()=>({usePermissions:()=>({isOwner:true,can:()=>true})}));
vi.mock("@/features/leads/api",async()=>({...await vi.importActual<typeof import("@/features/leads/api")>("@/features/leads/api"),getLeadLessApplicationSummary:mocks.summary,moveLeadLessApplicationToLoanManagement:mocks.move}));
vi.mock("@/features/bulk_import/BulkUploadModal",()=>({BulkUploadModal:()=> <div role="dialog" aria-label="Bulk Upload Leads"/>}));
beforeEach(()=>{
 mocks.request.mockReset();mocks.summary.mockReset();mocks.move.mockReset();
 mocks.summary.mockResolvedValue({application_id:"app-1",application_status:"submitted",documents_required:1,documents_verified:1,all_documents_verified:true});
 mocks.request.mockImplementation((url:string)=>Promise.resolve(url.includes("filter-options")?{}:url.includes("group_key")?{items:[{id:"app-1",application_code:"AFS-APP-000001",product_category:"loan",product_name:"Personal Loan",status:"submitted"}],total:1}:{items:[{id:"customer-1",name:"Direct Applicant",customer_code:"AFS-CUS-1",application_count:1}],total:1}));
});
function renderPage(){return render(<MemoryRouter><LeadListPage tab="document_collection"/></MemoryRouter>);}
async function expand(){await userEvent.click(await screen.findByRole("button",{name:"Expand"}));await screen.findByText("AFS-APP-000001");}
it("selects individual applications after expanding their customer and clears selection",async()=>{
 renderPage();await expand();await userEvent.click(screen.getByRole("checkbox",{name:"Select AFS-APP-000001"}));expect(screen.getByText(/1 Applications selected/)).toBeInTheDocument();await userEvent.click(screen.getByRole("button",{name:"Clear Selection"}));expect(screen.queryByRole("button",{name:"Assign Selected"})).not.toBeInTheDocument();
});
it("preserves the shared bulk upload entry point",async()=>{renderPage();await userEvent.click(screen.getByRole("button",{name:"Bulk Upload"}));expect(screen.getByRole("dialog",{name:"Bulk Upload Leads"})).toBeInTheDocument();});
it("opens the exact individual application and retains the customer link",async()=>{renderPage();await expand();expect(screen.getByRole("link",{name:"AFS-APP-000001"})).toHaveAttribute("href","/applications/app-1?from=document-collection");expect(screen.getByRole("link",{name:"AFS-CUS-1"})).toHaveAttribute("href","/customers/customer-1");});
it("does not offer Lead-only actions for an independent application",async()=>{renderPage();await expand();expect(screen.queryByRole("button",{name:"Generate Link"})).not.toBeInTheDocument();expect(screen.queryByRole("link",{name:"Edit Lead"})).not.toBeInTheDocument();});
it("retains the existing Move to Loan Management eligibility workflow",async()=>{renderPage();await expand();await userEvent.click(screen.getByRole("button",{name:"Update"}));expect(await screen.findByRole("heading",{name:"Move to Loan Management"})).toBeInTheDocument();await waitFor(()=>expect(mocks.summary).toHaveBeenCalledWith("app-1"));});
