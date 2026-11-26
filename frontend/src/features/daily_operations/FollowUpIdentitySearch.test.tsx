import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { FollowUpIdentitySearch } from "./FollowUpIdentitySearch";

const request=vi.hoisted(()=>vi.fn());
vi.mock("@/shared/api/client",()=>({apiRequest:request}));
beforeEach(()=>vi.clearAllMocks());
const label="Customer name, mobile, Customer ID, Application ID or Lead code";
it("searches first and opens only the explicitly selected Application workspace",async()=>{
 const selected=vi.fn();request.mockResolvedValueOnce({items:[{entity:"application",id:"a",code:"AFS-APP-A",customer_name:"Synthetic",workspace_status:"Existing workspace"},{entity:"application",id:"b",code:"AFS-APP-B",customer_name:"Synthetic",workspace_status:"Open linked workspace"}],has_more:false}).mockResolvedValueOnce({id:"existing-workspace",application_id:"b"});
 render(<FollowUpIdentitySearch onClose={vi.fn()} onStandalone={vi.fn()} onSelected={selected}/>);
 expect(request).not.toHaveBeenCalled();expect(screen.queryByText("Create Standalone / Unlinked record")).not.toBeInTheDocument();
 fireEvent.change(screen.getByLabelText(label),{target:{value:"AFS-CUS-SYN"}});fireEvent.click(screen.getByText("Search existing identities"));
 await screen.findByText(/AFS-APP-B/);expect(selected).not.toHaveBeenCalled();
 fireEvent.click(screen.getAllByRole("button",{name:"Open workspace"})[1]);
 await waitFor(()=>expect(selected).toHaveBeenCalledWith({id:"existing-workspace",application_id:"b"}));
 expect(JSON.parse(request.mock.calls[1][1].body)).toEqual({entity:"application",record_id:"b"});
});
it("allows a legitimate standalone after search and preserves search when a request fails",async()=>{
 const standalone=vi.fn();request.mockRejectedValueOnce(new Error("Review identity with Owner")).mockResolvedValueOnce({items:[],has_more:false});
 render(<FollowUpIdentitySearch onClose={vi.fn()} onStandalone={standalone} onSelected={vi.fn()}/>);
 fireEvent.change(screen.getByLabelText(label),{target:{value:"Synthetic new prospect"}});fireEvent.click(screen.getByText("Search existing identities"));
 expect(await screen.findByRole("alert")).toHaveTextContent("Review identity with Owner");expect(screen.getByLabelText(label)).toHaveValue("Synthetic new prospect");
 fireEvent.click(screen.getByText("Search existing identities"));fireEvent.click(await screen.findByText("Create Standalone / Unlinked record"));expect(standalone).toHaveBeenCalledOnce();
});
it("requires explicit verification for a Customer without an Application",async()=>{
 const standalone=vi.fn();request.mockResolvedValueOnce({items:[{entity:"customer",id:"c",code:"SYN-CUSTOMER",customer_name:"Synthetic Customer",mobile:"9000010000",workspace_status:"No application"}],has_more:false});
 render(<FollowUpIdentitySearch onClose={vi.fn()} onStandalone={standalone} onSelected={vi.fn()}/>);
 fireEvent.change(screen.getByLabelText(label),{target:{value:"SYN-CUSTOMER"}});fireEvent.click(screen.getByText("Search existing identities"));
 fireEvent.click(await screen.findByText("Review Customer without an Application"));
 expect(screen.getByText("Continue with verified Customer")).toBeDisabled();
 fireEvent.change(screen.getByLabelText("Owner identity verification reason"),{target:{value:"Owner verified synthetic Customer relationship"}});
 fireEvent.click(screen.getByLabelText("I verified this Customer relationship."));fireEvent.click(screen.getByText("Continue with verified Customer"));
 expect(standalone).toHaveBeenCalledWith({customer_name:"Synthetic Customer",customer_number:"9000010000",review_customer_id:"c",identity_review_reason:"Owner verified synthetic Customer relationship"});
 expect(request).toHaveBeenCalledTimes(1);
});
