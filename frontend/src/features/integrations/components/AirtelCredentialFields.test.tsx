import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {beforeEach,expect,it,vi} from "vitest";
import {useState} from "react";
import {AirtelCredentialFields} from "./AirtelCredentialFields";
const state=vi.hoisted(()=>({role:"owner",type:"primary"}));
vi.mock("@/features/auth/useAuth",()=>({useAuth:()=>state}));
vi.mock("@/features/owner/api",()=>({getOwnOwnerAccount:async()=>({owner_type:state.type})}));
beforeEach(()=>{state.role="owner";state.type="primary";});
function Fields(){const [values,setValues]=useState<Record<string,string>>({});return <AirtelCredentialFields saved={{username:"********",password:"********",customer_id:"********"}} values={values} onChange={(key,value)=>setValues(old=>({...old,[key]:value}))}/>;}
it("keeps saved values write-only, accepts three new values, and reveals only the typed password",async()=>{
 render(<Fields/>);await waitFor(()=>expect(screen.getByLabelText("Password")).toBeEnabled());
 expect(screen.getByLabelText("Customer ID")).toHaveAttribute("type","text");expect(screen.getByLabelText("Username")).toHaveAttribute("type","text");
 for(const label of ["Customer ID","Username","Password"])expect(screen.getByLabelText(label)).toHaveValue("");
 fireEvent.change(screen.getByLabelText("Password"),{target:{value:"typed-new-password"}});expect(screen.getByLabelText("Password")).toHaveAttribute("type","password");
 fireEvent.click(screen.getByRole("button",{name:"Show Airtel password"}));expect(screen.getByLabelText("Password")).toHaveAttribute("type","text");expect(screen.getByLabelText("Password")).toHaveValue("typed-new-password");
 fireEvent.click(screen.getByRole("button",{name:"Hide Airtel password"}));expect(screen.getByLabelText("Password")).toHaveAttribute("type","password");
});
it("disallows credential entry for a secondary owner",async()=>{state.type="secondary";render(<Fields/>);await screen.findByText("Only the Primary Owner can enter Airtel credentials.");expect(screen.getByLabelText("Password")).toBeDisabled();});
