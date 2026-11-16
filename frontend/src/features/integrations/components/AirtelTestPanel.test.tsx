import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { AirtelTestPanel } from "./AirtelTestPanel";
import { apiRequest } from "@/shared/api/client";

const state = vi.hoisted(() => ({ role: "owner" }));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => state }));
vi.mock("@/shared/api/client", () => ({ apiRequest: vi.fn() }));
beforeEach(() => { vi.resetAllMocks(); state.role = "owner"; });

it("does not send until an administrator supplies a mobile and confirms", async () => {
  vi.mocked(apiRequest).mockResolvedValue({ success: true, status: "accepted", error: null });
  const changed = vi.fn();
  render(<AirtelTestPanel configId="fixture" onChanged={changed} />);
  const button = screen.getByRole("button", { name: "Send test SMS" });
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Test mobile number"), { target: { value: "9000000077" } });
  expect(button).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/I authorize sending/));
  expect(button).toBeEnabled();
  expect(apiRequest).not.toHaveBeenCalled();
  fireEvent.click(button);
  await waitFor(() => expect(apiRequest).toHaveBeenCalledOnce());
  const [path, options] = vi.mocked(apiRequest).mock.calls[0];
  expect(path).toBe("/integration-configs/fixture/airtel-test-sms");
  expect(JSON.parse(options!.body as string)).toMatchObject({ mobile: "9000000077", confirm_send: true });
  await waitFor(() => expect(changed).toHaveBeenCalledWith(expect.stringContaining("Confirm receipt")));
});

it("requires separate explicit confirmation for owner cutover", async () => {
  vi.mocked(apiRequest).mockResolvedValue({ mode: "pin_only" });
  render(<AirtelTestPanel active alreadyVerified configId="fixture" onChanged={vi.fn()} />);
  const button = screen.getByRole("button", { name: "Enable customer PIN-only sign-in" });
  expect(button).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/I confirm all active customers/));
  fireEvent.click(button);
  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/auth/pin/cutover", { method: "POST" }));
  expect(await screen.findByText("PIN-only sign-in is enabled. Customer password sign-in is retired.")).toBeVisible();
});

it("does not present company cutover to other roles", () => {
  state.role = "employee";
  render(<AirtelTestPanel configId="fixture" onChanged={vi.fn()} />);
  expect(screen.queryByRole("button", { name: "Enable customer PIN-only sign-in" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Send test SMS" })).not.toBeInTheDocument();
});

it("verifies only an explicitly entered received OTP without exposing a generated code",async()=>{
 vi.mocked(apiRequest).mockResolvedValueOnce({success:true,status:"accepted",challenge_id:"a".repeat(64)}).mockResolvedValueOnce({verified:true});
 render(<AirtelTestPanel configId="fixture" onChanged={vi.fn()}/>);
 fireEvent.change(screen.getByLabelText("Test mobile number"),{target:{value:"9000000077"}});
 fireEvent.click(screen.getByLabelText(/I authorize sending/));fireEvent.click(screen.getByRole("button",{name:"Send test SMS"}));
 const otp=await screen.findByLabelText("Received test OTP");expect(otp).toHaveValue("");
 fireEvent.change(otp,{target:{value:"0472"}});fireEvent.click(screen.getByRole("button",{name:"Verify test OTP"}));
 await waitFor(()=>expect(apiRequest).toHaveBeenLastCalledWith("/integration-configs/fixture/airtel-verify-test-otp",expect.objectContaining({body:JSON.stringify({mobile:"9000000077",challenge_id:"a".repeat(64),otp:"0472"})})));
 expect(await screen.findByText(/Test OTP received and verified. You can now/)).toBeVisible();
});
it("shows an exact prerequisite and sends nothing while settings are disabled",()=>{
 render(<AirtelTestPanel configId="fixture" disabledReason="Enable this integration before sending a test SMS." onChanged={vi.fn()}/>);
 expect(screen.getByText("Enable this integration before sending a test SMS.")).toBeVisible();expect(screen.getByRole("button",{name:"Send test SMS"})).toBeDisabled();expect(apiRequest).not.toHaveBeenCalled();
});
