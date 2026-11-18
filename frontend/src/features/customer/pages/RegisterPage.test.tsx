import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RegisterPage } from "./RegisterPage";
import * as api from "../api";
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ setSession: vi.fn() }) }));
import * as pin from "@/features/auth/pinApi";

const { navigate } = vi.hoisted(() => ({ navigate: vi.fn() }));
vi.mock("react-router-dom", async () => ({ ...await vi.importActual("react-router-dom"), useNavigate: () => navigate }));
vi.mock("../api", () => ({ startDirectRegistration: vi.fn(), completeDirectRegistration: vi.fn() }));
vi.mock("@/features/auth/pinApi", () => ({ verifyPinOtp: vi.fn(), loginPin: vi.fn() }));
const challenge = { challenge_id: "fixture-challenge", masked_mobile: "******0088", expires_in: 600, resend_after: 60, message: "OTP submitted." };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.startDirectRegistration).mockResolvedValue(challenge);
  vi.mocked(pin.loginPin).mockResolvedValue({ access_token: "fixture-access", refresh_token: "fixture-refresh", role: "customer", user_id: "fixture-user", must_change_password: false, expires_in: 900, token_type: "bearer" });
  vi.mocked(pin.verifyPinOtp).mockResolvedValue({ authorization: "single-use-proof" });
  vi.mocked(api.completeDirectRegistration).mockResolvedValue(null);
});
function mount() { render(<MemoryRouter initialEntries={["/register?return=%2Fapply%2Ffixture"]}><RegisterPage /></MemoryRouter>); }
async function details(email = "") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Mobile Number"), "9000000088");
  if (email) await user.type(screen.getByLabelText("Email Address (optional)"), email);
  await user.type(screen.getByLabelText("Create 4-Digit PIN"), "0472");
  await user.type(screen.getByLabelText("Confirm 4-Digit PIN"), "0472");
  await user.click(screen.getByRole("button", { name: "Send OTP" }));
  return user;
}
describe("Customer registration", () => {
  it("shows only mobile, optional email and two secure PIN inputs", () => {
    mount();
    expect(screen.getAllByLabelText(/Mobile Number|Email Address|Digit PIN/)).toHaveLength(4);
    expect(screen.getByLabelText("Create 4-Digit PIN")).toHaveAttribute("type", "password");
    expect(screen.queryByLabelText(/Full Name|Password|Address$|City|State|PIN Code/)).not.toBeInTheDocument();
  });
  it.each(["", "customer@example.com"])("creates only after verified OTP; email %s", async email => {
    mount(); const user = await details(email);
    await screen.findByLabelText("4-digit SMS OTP");
    expect(api.startDirectRegistration).toHaveBeenCalledWith({ mobile: "9000000088", email: email || null, pin: "0472", confirm_pin: "0472" });
    expect(api.completeDirectRegistration).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Resend OTP in/ })).toBeDisabled();
    await user.type(screen.getByLabelText("4-digit SMS OTP"), "8621");
    await user.click(screen.getByRole("button", { name: "Verify OTP" }));
    await user.click(await screen.findByRole("button", { name: "Complete Registration" }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/apply/fixture", expect.objectContaining({ replace: true })));
    expect(api.completeDirectRegistration).toHaveBeenCalledWith(expect.objectContaining({ authorization: "single-use-proof", email: email || null, pin: "0472" }));
    expect(sessionStorage.length).toBe(0); expect(localStorage.length).toBe(0);
  });
  it("rejects mismatching PINs before sending", async () => {
    mount();
    fireEvent.change(screen.getByLabelText("Mobile Number"), { target: { value: "9000000088" } });
    fireEvent.change(screen.getByLabelText("Create 4-Digit PIN"), { target: { value: "0472" } });
    fireEvent.change(screen.getByLabelText("Confirm 4-Digit PIN"), { target: { value: "9999" } });
    await userEvent.click(screen.getByRole("button", { name: "Send OTP" }));
    expect(await screen.findByText("PIN confirmation does not match")).toBeVisible();
    expect(api.startDirectRegistration).not.toHaveBeenCalled();
  });
  it("shows submission failure without offering account completion", async () => {
    vi.mocked(api.startDirectRegistration).mockRejectedValue(new Error("SMS unavailable"));
    mount(); await details();
    await waitFor(() => expect(screen.getByRole("button", { name: "Send OTP" })).toBeEnabled());
    expect(screen.queryByLabelText("4-digit SMS OTP")).not.toBeInTheDocument();
    expect(api.completeDirectRegistration).not.toHaveBeenCalled();
  });
  it("blocks expired OTP and handles verification failure", async () => {
    vi.mocked(api.startDirectRegistration).mockResolvedValue({ ...challenge, expires_in: 0, resend_after: 0 });
    mount(); await details();
    expect(await screen.findByText("Code expired. Request a new code.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Verify OTP" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Resend OTP" })).toBeEnabled();
    expect(pin.verifyPinOtp).not.toHaveBeenCalled();
  });
});
