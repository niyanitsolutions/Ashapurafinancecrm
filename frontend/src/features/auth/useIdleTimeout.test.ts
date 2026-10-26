import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useIdleTimeout } from "./useIdleTimeout";

const mocks = vi.hoisted(() => ({ request: vi.fn().mockResolvedValue({}) }));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ accessToken: "synthetic-token" }) }));
vi.mock("@/shared/api/client", () => ({ apiRequest: mocks.request }));

beforeEach(() => { vi.useFakeTimers(); vi.clearAllMocks(); mocks.request.mockResolvedValue({}); });
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

it("never sends background heartbeats and expires once after ten idle minutes", () => {
  const expired = vi.fn();
  renderHook(() => useIdleTimeout(expired));
  act(() => { vi.advanceTimersByTime(11 * 60000); });
  expect(expired).toHaveBeenCalledTimes(1);
  expect(mocks.request).not.toHaveBeenCalled();
});

it("sends throttled activity only for trusted visible interactions", () => {
  const listeners = vi.spyOn(window, "addEventListener");
  renderHook(() => useIdleTimeout(vi.fn()));
  const callback = listeners.mock.calls.find(([event]) => event === "click")![1] as EventListener;
  act(() => callback({ isTrusted: false } as Event));
  expect(mocks.request).not.toHaveBeenCalled();
  act(() => { callback({ isTrusted: true } as Event); callback({ isTrusted: true } as Event); });
  expect(mocks.request).toHaveBeenCalledTimes(1);
  expect(mocks.request).toHaveBeenCalledWith("/auth/activity", { method: "POST" });
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
  act(() => { vi.advanceTimersByTime(31000); callback({ isTrusted: true } as Event); });
  expect(mocks.request).toHaveBeenCalledTimes(1);
});

it("resets from server confirmation without extending server activity", () => {
  const expired = vi.fn();
  const { result } = renderHook(() => useIdleTimeout(expired));
  act(() => { vi.advanceTimersByTime(9 * 60000); });
  expect(result.current.isWarning).toBe(true);
  act(() => result.current.resetFromServer());
  expect(result.current.isWarning).toBe(false);
  expect(mocks.request).not.toHaveBeenCalled();
});
