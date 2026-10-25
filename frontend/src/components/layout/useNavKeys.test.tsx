import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import { useNavKeys } from "./useNavKeys";

const mocks = vi.hoisted(() => ({ userId: "synthetic-owner", getNav: vi.fn() }));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ userId: mocks.userId }) }));
vi.mock("@/features/dashboard/api", () => ({ getNav: mocks.getNav }));

it("does not reuse an Owner's cached navigation when another account signs in", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  mocks.getNav.mockResolvedValueOnce([{ key: "daily_progress" }]).mockResolvedValueOnce([{ key: "daily_issues" }]);
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const { result, rerender } = renderHook(() => useNavKeys(), { wrapper });
  await waitFor(() => expect(result.current?.has("daily_progress")).toBe(true));
  mocks.userId = "synthetic-employee"; rerender();
  expect(result.current?.has("daily_progress")).not.toBe(true);
  await waitFor(() => expect(result.current?.has("daily_issues")).toBe(true));
  expect(result.current?.has("daily_progress")).toBe(false);
});
