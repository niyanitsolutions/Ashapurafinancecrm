vi.mock("@/features/auth/useAuth",()=>({useAuth:()=>({role:"owner"})}));
vi.mock("@/features/owner/api",()=>({getOwnOwnerAccount:async()=>({owner_type:"primary"})}));
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { IntegrationListPage } from "./pages/IntegrationListPage";
import { fieldsFor } from "./providerFields";
const mocks = vi.hoisted(() => ({ create: vi.fn(), draft: vi.fn(), list: vi.fn() }));
vi.mock("./api", () => ({ listIntegrationConfigs: mocks.list, listIntegrationProviders: async () => [{ id: "airtel", integration_type: "sms", provider: "airtel_iq", label: "Airtel IQ" }], createIntegrationConfig: mocks.create, testDraftConnection: mocks.draft, testIntegrationConnection: vi.fn() }));
beforeEach(() => { vi.clearAllMocks(); mocks.list.mockResolvedValue([]); mocks.create.mockResolvedValue({ id: "draft", webhook_callback_path: null }); mocks.draft.mockResolvedValue({ success: false, error_message: "Contract pending. No SMS was sent.", checks: null }); });
async function form() {
  render(<MemoryRouter><IntegrationListPage /></MemoryRouter>); fireEvent.click(screen.getByRole("button", { name: "+ Add Configuration" }));
  const dialog = within(screen.getByRole("dialog")); await waitFor(() => expect(dialog.getByRole("option", {name:/^SMS$/})).toBeInTheDocument()); fireEvent.change(dialog.getAllByRole("combobox")[0], { target: { value: "sms" } }); await waitFor(() => expect(dialog.getByRole("option", {name:"Airtel IQ"})).toBeInTheDocument()); fireEvent.change(dialog.getAllByRole("combobox")[1], { target: { value: "airtel_iq" } });
  await waitFor(()=>expect(dialog.getByLabelText("Customer ID")).toBeEnabled());
  return dialog;
}
it("shows approved defaults and fully sensitive credential inputs", async () => {
  const dialog = await form(); expect(dialog.getByLabelText("Username")).toHaveAttribute("type","text"); expect(dialog.getByLabelText("Password")).toHaveAttribute("type","password"); expect(dialog.getByLabelText("API Endpoint")).toHaveValue("https://iqsms.airtel.in/api/v1/send-prepaid-sms"); expect(dialog.getByLabelText("Sender ID")).toHaveValue("ASHFNS"); expect(dialog.getByLabelText("DLT Template ID")).toHaveValue("1077151820081508033"); expect(dialog.getByLabelText("DLT Entity ID")).toHaveValue("1001474305342749488"); for(const label of ["Customer ID","Username"])
    expect(dialog.getByLabelText(label)).toHaveAttribute("type", "text"); expect(dialog.getByLabelText("Message Type")).toHaveValue("TRANSACTIONAL"); expect(dialog.getByRole("status")).toHaveTextContent("Airtel uses HTTP Basic authentication");
});
it("saves encrypted-backend draft without inventing a successful connection", async () => {
  const dialog = await form(); fireEvent.change(dialog.getByPlaceholderText("Name (e.g. Meta Production)"), { target: { value: "Airtel Production draft" } }); for(const label of ["Customer ID","Username","Password"])
    fireEvent.change(dialog.getByLabelText(label), { target: { value: "synthetic credential" } }); fireEvent.click(dialog.getByRole("button", { name: "Save Configuration" })); await waitFor(() => expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ provider: "airtel_iq", config: expect.objectContaining({ sender_id: "ASHFNS" }) }))); expect(mocks.draft).not.toHaveBeenCalled();
});
it("uses the Airtel provider on test and does not display successful connection", async () => {
  const dialog = await form(); fireEvent.change(dialog.getByPlaceholderText("Name (e.g. Meta Production)"), { target: { value: "Airtel draft" } }); for(const label of ["Customer ID","Username","Password"])
    fireEvent.change(dialog.getByLabelText(label), { target: { value: "synthetic credential" } }); fireEvent.click(dialog.getByRole("button", { name: /Validate Configuration/i })); await waitFor(() => expect(mocks.draft).toHaveBeenCalledWith(expect.objectContaining({ provider: "airtel_iq" }))); expect(await screen.findByText("Contract pending. No SMS was sent.")).toBeVisible(); expect(screen.queryByText("Connected successfully.")).not.toBeInTheDocument();
});
it("preserves the existing SMS field set for other providers", () => { expect(fieldsFor("sms", "msg91").some(field => field.key === "auth_key")).toBe(true); expect(fieldsFor("sms", "generic_sms").some(field => field.key === "api_key")).toBe(true); });

it("uses HTTP submission success without asking for invented response JSON fields",async()=>{
 const dialog=await form();
 expect(dialog.queryByLabelText("Confirmed response success field path")).not.toBeInTheDocument();
 expect(dialog.queryByLabelText("Confirmed success value (JSON scalar)")).not.toBeInTheDocument();
 expect(dialog.queryByLabelText("Authorization header value (exact, confirmed by Airtel)")).not.toBeInTheDocument();
 expect(dialog.getByLabelText("Account-specific API contract confirmed")).toBeDisabled();
});
