import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PinAuthPanel } from "./PinAuthPanel";
import * as api from "../pinApi";
import {ApiError} from "@/shared/api/client";

const { session, navigate } = vi.hoisted(() => ({ session: vi.fn(), navigate: vi.fn() }));
vi.mock("../useAuth", () => ({ useAuth: () => ({ setSession: session }) }));
vi.mock("react-router-dom", async () => ({ ...await vi.importActual("react-router-dom"), useNavigate: () => navigate }));
vi.mock("../pinApi", () => ({ pinPolicy: vi.fn(), startPin: vi.fn(), verifyPinOtp: vi.fn(), finishPin: vi.fn(), loginPin: vi.fn() }));
vi.mock("@/shared/geolocation", () => ({ getCurrentCoordinates: () => Promise.resolve(null) }));
const login = { access_token: "access", refresh_token: "refresh", role: "customer", user_id: "user", must_change_password: false, expires_in: 900, token_type: "bearer" as const };
const challenge = { challenge_id: "fixture-challenge", masked_mobile: "******0077", expires_in: 600, resend_after: 60, message: "If eligible, a code will arrive." };

function mount(returnTo: string | null = null) {
  return render(<MemoryRouter><PinAuthPanel returnTo={returnTo} onLegacy={vi.fn()} /></MemoryRouter>);
}
async function start(purpose = "First-time verification / Create PIN") {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: purpose }));
  await user.type(screen.getByLabelText("Registered mobile number"), "9000000077");
  await user.click(screen.getByRole("button", { name: "Send verification code" }));
  await screen.findByLabelText("4-digit OTP");
  return user;
}
async function verify() {
  const user = await start();
  await user.type(screen.getByLabelText("4-digit OTP"), "8621");
  await user.click(screen.getByRole("button", { name: "Verify OTP" }));
  await screen.findByLabelText("New 4-digit PIN");
  return user;
}
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.pinPolicy).mockResolvedValue({ mode: "pin_only" });
  vi.mocked(api.startPin).mockResolvedValue(challenge);
  vi.mocked(api.verifyPinOtp).mockResolvedValue({ authorization: "single-use-proof" });
  vi.mocked(api.loginPin).mockResolvedValue(login);
  vi.mocked(api.finishPin).mockResolvedValue(login);
});

describe("PIN sign in", () => {
  it("blocks an expired code and lets the user explicitly request a replacement", async () => {
    vi.mocked(api.startPin).mockResolvedValueOnce({ ...challenge, expires_in: 0, resend_after: 0 });
    mount();
    const user = await start();
    expect(screen.getByText("Code expired. Request a new code.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Verify OTP" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Resend OTP" }));
    await waitFor(() => expect(api.startPin).toHaveBeenCalledTimes(2));
    expect(api.verifyPinOtp).not.toHaveBeenCalled();
  });
  it("uses a masked four-digit PIN, creates a session without OTP, and rejects external return URLs", async () => {
    mount("//untrusted.example");
    const user = userEvent.setup();
    const pin = screen.getByLabelText("4-digit PIN");
    expect(pin).toHaveAttribute("type", "password");
    expect(pin).toHaveAttribute("maxLength", "4");
    await user.type(screen.getByLabelText("Registered mobile number"), "9000000077");
    await user.type(pin, "0472");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(session).toHaveBeenCalledOnce());
    expect(api.loginPin).toHaveBeenCalledWith("9000000077", "0472", null);
    expect(api.startPin).not.toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith("/", { replace: true });
    expect(screen.queryByText(/password sign-in/)).not.toBeInTheDocument();
  });

  it("does not authenticate until OTP and matching PIN setup finish", async () => {
    mount("/portal");
    const user = await verify();
    expect(api.startPin).toHaveBeenCalledWith("9000000077", "FIRST_TIME_LOGIN");
    expect(session).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Confirm PIN")).toHaveAttribute("type", "password");
    await user.type(screen.getByLabelText("New 4-digit PIN"), "0472");
    await user.type(screen.getByLabelText("Confirm PIN"), "5678");
    await user.click(screen.getByRole("button", { name: "Save PIN" }));
    expect(await screen.findByText("PIN confirmation does not match.")).toBeInTheDocument();
    expect(api.finishPin).not.toHaveBeenCalled();
    await user.clear(screen.getByLabelText("Confirm PIN"));
    await user.type(screen.getByLabelText("Confirm PIN"), "0472");
    await user.click(screen.getByRole("button", { name: "Save PIN" }));
    await waitFor(() => expect(session).toHaveBeenCalledOnce());
    expect(api.finishPin).toHaveBeenCalledWith("single-use-proof", "0472", "0472", null);
    expect(navigate).toHaveBeenCalledWith("/portal", { replace: true });
  });

  it("resets with a separate purpose and returns to login without a session", async () => {
    vi.mocked(api.finishPin).mockResolvedValue({ message: "PIN reset" });
    mount();
    const user = await start("Forgot PIN");
    expect(api.startPin).toHaveBeenCalledWith("9000000077", "FORGOT_PIN");
    expect(screen.getByRole("button", { name: "Resend in 60s" })).toBeDisabled();
    await user.type(screen.getByLabelText("4-digit OTP"), "8621");
    await user.click(screen.getByRole("button", { name: "Verify OTP" }));
    await user.type(await screen.findByLabelText("New 4-digit PIN"), "5938");
    await user.type(screen.getByLabelText("Confirm PIN"), "5938");
    await user.click(screen.getByRole("button", { name: "Save PIN" }));
    expect(await screen.findByRole("heading", { name: "PIN reset successful" })).toBeInTheDocument();
    expect(session).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Return to login" }));
    expect(screen.getByLabelText("4-digit PIN")).toHaveValue("");
  });

  it("blocks duplicate submissions while showing safe delivery errors", async () => {
    let reject!: (error: Error) => void;
    vi.mocked(api.startPin).mockReturnValue(new Promise((_, no) => { reject = no; }));
    mount();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Forgot PIN" }));
    await user.type(screen.getByLabelText("Registered mobile number"), "9000000077");
    const button = screen.getByRole("button", { name: "Send verification code" });
    fireEvent.submit(button.closest("form")!);
    fireEvent.submit(button.closest("form")!);
    expect(api.startPin).toHaveBeenCalledOnce();
    await act(async () => reject(new ApiError("pin_throttled", "Too many attempts. Try later.")));
    expect(await screen.findByText("Too many attempts. Try later.")).toBeInTheDocument();
    expect(session).not.toHaveBeenCalled();
  });
});
