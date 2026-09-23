import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { usePermissions } from "./usePermissions";

const auth = vi.hoisted(() => ({ role: "employee", userId: "employee-a" }));
const getMyPermissions = vi.hoisted(() => vi.fn());

vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => auth }));
vi.mock("@/features/access_control/api", () => ({ getMyPermissions }));

describe("usePermissions", () => {
  beforeEach(() => {
    auth.role = "employee";
    auth.userId = "employee-a";
    getMyPermissions.mockReset();
  });

  it("does not reuse one employee's cached grants for another employee", async () => {
    getMyPermissions
      .mockResolvedValueOnce({ grants: {} })
      .mockResolvedValueOnce({ grants: { "insurance_management:recruitment": ["view", "create"] } });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result, rerender } = renderHook(() => usePermissions(), { wrapper });

    await waitFor(() => expect(getMyPermissions).toHaveBeenCalledTimes(1));
    expect(result.current.can("insurance_management:recruitment", "create")).toBe(false);

    auth.userId = "employee-b";
    rerender();

    await waitFor(() => expect(getMyPermissions).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.can("insurance_management:recruitment", "create")).toBe(true));
  });

  it("loads the employee's grants after switching from an Owner session", async () => {
    auth.role = "owner";
    auth.userId = "owner-a";
    getMyPermissions.mockResolvedValue({
      grants: { "insurance_management:recruitment": ["view", "create", "edit"] },
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result, rerender } = renderHook(() => usePermissions(), { wrapper });

    expect(result.current.can("insurance_management:recruitment", "create")).toBe(true);
    expect(getMyPermissions).not.toHaveBeenCalled();

    auth.role = "employee";
    auth.userId = "employee-a";
    rerender();

    await waitFor(() => expect(getMyPermissions).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(result.current.can("insurance_management:recruitment", "edit")).toBe(true));
  });
});
