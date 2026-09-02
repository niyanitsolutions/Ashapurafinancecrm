import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AuthContext, type AuthContextValue } from "@/features/auth/authContext";
import { useListDelete } from "@/features/bin/useListDelete";

const deleteRecord = vi.fn(() => Promise.resolve({}));
const bulkDeleteRecords = vi.fn(() => Promise.resolve({ deleted: [], skipped: [] }));
vi.mock("@/features/bin/api", () => ({
  deleteRecord: (...a: unknown[]) => deleteRecord(...(a as [])),
  bulkDeleteRecords: (...a: unknown[]) => bulkDeleteRecords(...(a as [])),
}));

function Harness({ onChanged }: { onChanged?: () => void }) {
  const del = useListDelete("leads", onChanged ?? (() => {}));
  return (
    <div>
      <span data-testid="enabled">{String(del.enabled)}</span>
      {del.enabled && (
        <>
          <button onClick={() => del.toggle("a")}>toggle-a</button>
          <button onClick={() => del.toggle("b")}>toggle-b</button>
          <button onClick={() => del.requestBulkDelete()}>bulk</button>
          <button onClick={() => del.requestDelete("x")}>one</button>
        </>
      )}
      {del.bulkBar}
      {del.dialog}
    </div>
  );
}

function renderAs(role: string, onChanged?: () => void) {
  const value = { role, user: null, isAuthenticated: true } as unknown as AuthContextValue;
  return render(
    <AuthContext.Provider value={value}>
      <Harness onChanged={onChanged} />
    </AuthContext.Provider>,
  );
}

describe("useListDelete", () => {
  it("is disabled for a non-Owner — no affordances render", () => {
    renderAs("employee");
    expect(screen.getByTestId("enabled")).toHaveTextContent("false");
    expect(screen.queryByRole("button", { name: "one" })).not.toBeInTheDocument();
  });

  it("Owner: single delete goes through the confirm dialog and calls the API once", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    renderAs("owner", onChanged);

    await user.click(screen.getByRole("button", { name: "one" }));
    expect(await screen.findByText("Delete this record?")).toBeInTheDocument();
    expect(deleteRecord).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(deleteRecord).toHaveBeenCalledWith("leads", "x");
    expect(onChanged).toHaveBeenCalled();
  });

  it("Owner: bulk bar appears once rows are selected and drives a single bulk call", async () => {
    const user = userEvent.setup();
    renderAs("owner");

    await user.click(screen.getByRole("button", { name: "toggle-a" }));
    await user.click(screen.getByRole("button", { name: "toggle-b" }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "bulk" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Delete 2 records?")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(bulkDeleteRecords).toHaveBeenCalledWith("leads", ["a", "b"]);
  });
});
