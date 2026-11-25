import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/shared/api/client";
import { SubmittedApplicationDetails } from "./SubmittedApplicationDetails";
import { updateSubmittedApplication, type ApplicationDetail, type FormDefinition, type FormField } from "../api";
let allowed=true;
vi.mock("@/features/access_control/usePermissions",()=>({usePermissions:()=>({can:()=>allowed})}));
vi.mock("../api",async()=>({...await vi.importActual("../api"),updateSubmittedApplication:vi.fn()}));
const fields=[{key:"full_name",label:"Full Name",field_type:"text",required:true},{key:"salary",label:"Monthly Net Salary",field_type:"number",required:false},{key:"company",label:"Company Name",field_type:"text",required:false},{key:"address",label:"Current Address",field_type:"textarea",required:false},{key:"gender",label:"Gender",field_type:"select",options:["Male","Female","Other"],required:false},{key:"dob",label:"Date Of Birth",field_type:"date",required:false}].map(f=>({options:null,section:null,...f})) as FormField[];
const schema={fields,repeatable_groups:[],required_documents:[]} as unknown as FormDefinition;
const application={id:"app-1",application_code:"AFS-APP-1",customer_id:"customer-1",version:4,form_data:{full_name:"Original Applicant",salary:30000,company:"Original employer",address:"Saved address",gender:"Male",dob:"2003-08-26",legacy:"Retain historical field"}} as unknown as ApplicationDetail;
beforeEach(()=>{allowed=true;vi.mocked(updateSubmittedApplication).mockReset();vi.mocked(updateSubmittedApplication).mockResolvedValue({...application,version:5,form_data:{...application.form_data,salary:45000}});});
function mount(){const saved=vi.fn();render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter><SubmittedApplicationDetails application={application} schema={schema} onSaved={saved}/></MemoryRouter></QueryClientProvider>);return saved;}
it("edits every saved schema field and sends only changed application answers",async()=>{
 const saved=mount();const user=userEvent.setup();await user.click(screen.getByRole("button",{name:"Edit Details"}));
 for(const field of fields)expect(screen.getByLabelText(new RegExp(field.label))).toBeVisible();
 expect(screen.getByLabelText(/Full Name/)).toHaveValue("Original Applicant");expect(screen.getByLabelText("Monthly Net Salary")).toHaveValue(30000);
 await user.clear(screen.getByLabelText("Monthly Net Salary"));await user.type(screen.getByLabelText("Monthly Net Salary"),"45000");await user.type(screen.getByLabelText("Reason for correction"),"Correct the submitted salary");await user.click(screen.getByRole("button",{name:"Save Changes"}));
 await waitFor(()=>expect(updateSubmittedApplication).toHaveBeenCalledWith("app-1",{salary:45000},4,"Correct the submitted salary"));expect(saved).toHaveBeenCalledWith(expect.objectContaining({version:5}));expect(await screen.findByText("Application details saved.")).toBeVisible();
 expect(application.form_data.salary).toBe(30000);
});
it("cancel restores the original display without saving",async()=>{mount();const user=userEvent.setup();await user.click(screen.getByRole("button",{name:"Edit Details"}));await user.clear(screen.getByLabelText(/Full Name/));await user.type(screen.getByLabelText(/Full Name/),"Unsaved replacement");await user.click(screen.getByRole("button",{name:"Cancel"}));expect(screen.getByText("Original Applicant")).toBeVisible();expect(screen.queryByText("Unsaved replacement")).not.toBeInTheDocument();expect(updateSubmittedApplication).not.toHaveBeenCalled();});
it("retains entered values and displays server field-level validation errors",async()=>{vi.mocked(updateSubmittedApplication).mockRejectedValue(new ApiError("validation_error","Check fields",{field_errors:{salary:"Salary needs review."}}));mount();const user=userEvent.setup();await user.click(screen.getByRole("button",{name:"Edit Details"}));fireEvent.change(screen.getByLabelText("Monthly Net Salary"),{target:{value:"45000"}});await user.type(screen.getByLabelText("Reason for correction"),"Review salary");await user.click(screen.getByRole("button",{name:"Save Changes"}));expect(await screen.findByText("Salary needs review.")).toBeVisible();expect(screen.getByLabelText("Monthly Net Salary")).toHaveValue(45000);});
it("does not offer editing without the existing Customer edit permission",()=>{allowed=false;mount();expect(screen.queryByRole("button",{name:"Edit Details"})).not.toBeInTheDocument();expect(screen.getByText("Original Applicant")).toBeVisible();});
