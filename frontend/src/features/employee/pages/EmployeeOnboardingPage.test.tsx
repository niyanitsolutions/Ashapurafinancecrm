import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import {beforeEach,expect,it,vi} from "vitest";
import {EmployeeOnboardingPage} from "./EmployeeOnboardingPage";
import * as api from "../hrApi";
const state=vi.hoisted(()=>({role:"employee"}));
vi.mock("@/features/auth/useAuth",()=>({useAuth:()=>state}));
vi.mock("../hrApi",()=>({getHrProfile:vi.fn(),saveHrProfile:vi.fn(),submitHrProfile:vi.fn(),reviewHrProfile:vi.fn()}));
vi.mock("../components/EmployeeEditRequests",()=>({EmployeeEditRequests:()=>null}));
vi.mock("../components/EmployeeHrDocuments",()=>({EmployeeHrDocuments:()=> <div>Private document workflow</div>}));
const row={employee_id:"employee",employee_code:"EMP-1",mobile:"9111111111",account_status:"active",current_profile:{first_name:"Jane",last_name:"Doe",email:"jane@example.com"},onboarding:{status:"incomplete",version:0,history:[]}};
beforeEach(()=>{vi.resetAllMocks();state.role="employee";vi.mocked(api.getHrProfile).mockResolvedValue(row);});
it("keeps emergency contact distinct and conditionally requests experience and permanent address",async()=>{
 render(<MemoryRouter><EmployeeOnboardingPage/></MemoryRouter>);
 expect(await screen.findByLabelText("Registered mobile number")).toHaveValue("9111111111");
 expect(screen.getByLabelText("Emergency contact mobile")).toHaveValue("");
 expect(screen.queryByLabelText("Previous company")).not.toBeInTheDocument();
 fireEvent.click(screen.getByLabelText("Fresher"));expect(screen.getByLabelText("Previous company")).toBeRequired();
 expect(screen.getByLabelText("Permanent address")).toBeInTheDocument();
 fireEvent.click(screen.getByLabelText("Permanent address same as local address"));expect(screen.queryByLabelText("Permanent address")).not.toBeInTheDocument();
 expect(screen.queryByRole("button",{name:"Approve completed profile"})).not.toBeInTheDocument();
});
it("shows pending verification without offering self approval or blocking CRM access",async()=>{
 vi.mocked(api.getHrProfile).mockResolvedValue({...row,onboarding:{status:"pending_verification",version:2,history:[]}});
 render(<MemoryRouter><EmployeeOnboardingPage/></MemoryRouter>);
 await screen.findByText(/Account status: active/);
 expect(screen.getByLabelText("First name")).toBeDisabled();
 expect(screen.queryByRole("button",{name:"Approve completed profile"})).not.toBeInTheDocument();
 expect(screen.getByText(/retain authorized CRM access/)).toBeVisible();
});
it("renders a safe error state when profile access is denied",async()=>{
 vi.mocked(api.getHrProfile).mockRejectedValue(new Error("denied"));
 render(<MemoryRouter><EmployeeOnboardingPage/></MemoryRouter>);
 await waitFor(()=>expect(screen.getByText("Unable to load profile.")).toBeInTheDocument());
 expect(screen.queryByRole("button",{name:"Save profile"})).not.toBeInTheDocument();
});
