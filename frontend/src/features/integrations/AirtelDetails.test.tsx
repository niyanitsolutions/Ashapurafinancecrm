vi.mock("@/features/owner/api",()=>({getOwnOwnerAccount:async()=>({owner_type:"primary"})}));
import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {MemoryRouter,Routes,Route} from "react-router-dom";
import {beforeEach,expect,it,vi} from "vitest";
import type {IntegrationConfig} from "./api";
import {IntegrationDetailsPage} from "./pages/IntegrationDetailsPage";
const mocks=vi.hoisted(()=>({get:vi.fn(),update:vi.fn(),test:vi.fn(),logs:vi.fn()}));
vi.mock("@/features/auth/useAuth",()=>({useAuth:()=>({role:"owner"})}));
vi.mock("./api",async original=>({...await original<typeof import("./api")>(),getIntegrationConfig:mocks.get,updateIntegrationConfig:mocks.update,testIntegrationConnection:mocks.test,listIntegrationTestLogs:mocks.logs}));
const endpoint="https://iqsms.airtel.in/api/v1/send-prepaid-sms";
let row:IntegrationConfig;
beforeEach(()=>{vi.resetAllMocks();mocks.logs.mockResolvedValue([]);row={id:"fixture",name:"Airtel",provider:"airtel_iq",integration_type:"sms",config:{api_url:endpoint,customer_id:"********",authorization_value:"********",sender_id:"ASHFNS",dlt_template_id:"1077151820081508033",entity_id:"AIR7316372024",message_type:"TRANSACTIONAL",destination_template:'["{{mobile}}"]',contract_confirmed:"false"},airtel_workflow:{expected_endpoint:endpoint,validated_at:null,verified_at:null,challenge_id:null},is_enabled:false,is_active:false,integration_code:"AFS-INTG-TEST",last_tested_at:null,last_failure_at:null,last_error_message:null,activated_at:null,webhook_verified_at:null,health_status:null,created_at:"2026-11-16",updated_at:"2026-11-16",webhook_callback_path:null,last_success_at:null};mocks.get.mockImplementation(async()=>row);mocks.update.mockImplementation(async(_id,payload)=>{row={...row,config:{...row.config,...payload.config}};return row;});mocks.test.mockImplementation(async()=>{row={...row,airtel_workflow:{...row.airtel_workflow!,validated_at:"2026-11-16"}};return {success:true,kind:"configuration_validation",error_message:"Configuration validation successful. No SMS was sent.",checks:null};});});
function mount(){return render(<MemoryRouter initialEntries={["/integrations/fixture"]}><Routes><Route path="/integrations/:configId" element={<IntegrationDetailsPage/>}/></Routes></MemoryRouter>);}
it("hydrates endpoint independently, prevents autofill edits, and preserves it after save/reload",async()=>{
 const app=mount();const url=await screen.findByLabelText("API Endpoint");expect(url).toHaveValue(endpoint);expect(url).toHaveAttribute("readonly");expect(url).toHaveAttribute("name","airtel_iq-api_url");await waitFor(()=>expect(screen.getByLabelText("Customer ID")).toBeEnabled());expect(screen.getByLabelText("Customer ID")).toHaveValue("");
 fireEvent.change(screen.getByLabelText("Customer ID"),{target:{value:"synthetic-new-customer"}});fireEvent.click(screen.getByRole("button",{name:"Save Changes"}));
 await waitFor(()=>expect(mocks.update).toHaveBeenCalledWith("fixture",{config:{customer_id:"synthetic-new-customer"}}));
 app.unmount();mount();expect(await screen.findByLabelText("API Endpoint")).toHaveValue(endpoint);
});
it("enables persistent explicit contract confirmation only after successful local validation",async()=>{
 mount();expect(await screen.findByLabelText("Account-specific API contract confirmed")).toBeDisabled();
 fireEvent.click(screen.getByRole("button",{name:"Validate Configuration (no SMS)"}));
 await waitFor(()=>expect(screen.getByLabelText("Account-specific API contract confirmed")).toBeEnabled());
 fireEvent.change(screen.getByLabelText("Account-specific API contract confirmed"),{target:{value:"true"}});fireEvent.click(screen.getByRole("button",{name:"Save Changes"}));
 await waitFor(()=>expect(mocks.update).toHaveBeenCalledWith("fixture",{config:{contract_confirmed:"true"}}));
 expect(screen.getByRole("button",{name:"Set Active"})).toBeDisabled();
});

it("shows sanitized HTTP diagnostics in history without implying delivery or retry",async()=>{
 mocks.logs.mockResolvedValue([{id:"failed",success:false,kind:"sms_submission",submission_status:"rejected",response_time_ms:209,error_message:"Airtel returned HTTP 401; submission was not accepted.",tested_at:"2026-11-16T07:00:00Z",diagnostics:{http_status:401,outcome_type:"http_non_200",response_format:"json",response_excerpt:'{"message":"Invalid customer id [redacted]"}'}}]);
 mount();expect(await screen.findByText("Airtel returned HTTP 401; submission was not accepted.")).toBeVisible();
 expect(screen.getByText(/HTTP: 401 - Outcome: http_non_200/)).toBeVisible();
 fireEvent.click(screen.getByText("Sanitized Airtel response"));expect(screen.getByText('{"message":"Invalid customer id [redacted]"}')).toBeVisible();
 expect(screen.getByRole("button",{name:"Set Active"})).toBeDisabled();
});

it("keeps send and activation blocked when Airtel authentication is unconfirmed",async()=>{
 row.airtel_workflow={...row.airtel_workflow!,authentication_ready:false,authentication_message:"Airtel authentication is awaiting confirmation."};
 mount();await screen.findByLabelText("API Endpoint");
 fireEvent.change(screen.getByLabelText("Test mobile number"),{target:{value:"9000000088"}});fireEvent.click(screen.getByLabelText(/I authorize sending/));
 expect(screen.getByRole("button",{name:"Send test SMS"})).toBeDisabled();expect(screen.getByRole("button",{name:"Set Active"})).toBeDisabled();
 expect(screen.getAllByText("Airtel authentication is awaiting confirmation.").length).toBeGreaterThan(0);
});
