import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { DocumentPassword } from "./DocumentPassword";
const state=vi.hoisted(()=>({allowed:true,user:"employee",request:vi.fn()}));
vi.mock("@/features/access_control/usePermissions",()=>({usePermissions:()=>({can:()=>state.allowed})}));
vi.mock("@/features/auth/useAuth",()=>({useAuth:()=>({userId:state.user})}));
vi.mock("@/shared/api/client",()=>({apiRequest:state.request}));
beforeEach(()=>{state.allowed=true;state.user="employee";state.request.mockReset();state.request.mockResolvedValue({password:"mock-document-secret"});});
it("masks by default, reveals only on demand and hides without persistent storage",async()=>{
 render(<DocumentPassword applicationId="a1" documentId="d1"/>);
 expect(screen.queryByText(/mock-document-secret/)).not.toBeInTheDocument();expect(state.request).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole("button",{name:"Show Password"}));
 expect(await screen.findByText(/mock-document-secret/)).toBeVisible();
 expect(state.request).toHaveBeenCalledWith("/applications/a1/documents/d1/password",{cache:"no-store"});
 fireEvent.click(screen.getByRole("button",{name:"Hide Password"}));expect(screen.queryByText(/mock-document-secret/)).not.toBeInTheDocument();
 expect(localStorage.length).toBe(0);expect(sessionStorage.length).toBe(0);
});
it("clears on permission loss, document change and window blur",async()=>{
 const view=render(<DocumentPassword applicationId="a1" documentId="d1"/>);
 fireEvent.click(screen.getByRole("button"));await screen.findByText(/mock-document-secret/);
 fireEvent(window,new Event("blur"));expect(screen.queryByText(/mock-document-secret/)).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole("button"));await screen.findByText(/mock-document-secret/);
 state.allowed=false;view.rerender(<DocumentPassword applicationId="a1" documentId="d1"/>);expect(screen.queryByRole("button")).not.toBeInTheDocument();
 state.allowed=true;view.rerender(<DocumentPassword applicationId="a2" documentId="d2"/>);expect(screen.queryByText(/mock-document-secret/)).not.toBeInTheDocument();
});
it("discards an in-flight response after leaving or losing authorization",async()=>{
 let finish!:(value:{password:string})=>void;state.request.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
 const view=render(<DocumentPassword applicationId="a1" documentId="d1"/>);fireEvent.click(screen.getByRole("button"));
 state.allowed=false;view.rerender(<DocumentPassword applicationId="a1" documentId="d1"/>);
 await act(async()=>finish({password:"late-secret"}));expect(screen.queryByText(/late-secret/)).not.toBeInTheDocument();
 view.unmount();
});
it("uses a safe error without displaying the server response",async()=>{
 state.request.mockRejectedValue(new Error("sensitive response"));render(<DocumentPassword applicationId="a1" documentId="d1"/>);fireEvent.click(screen.getByRole("button"));
 await waitFor(()=>expect(screen.getByRole("alert")).toHaveTextContent("Unable to reveal"));expect(screen.queryByText(/sensitive response/)).not.toBeInTheDocument();
});
