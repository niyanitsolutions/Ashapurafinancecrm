import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CaseTimelineEntry } from "@/features/loan_management/api";
import { FollowUpHistory } from "./FollowUpHistory";

// The colour is computed from the IST calendar date at render time. Freeze "now" to a
// fixed IST day so Past/Today/Future are deterministic.
const FIXED_NOW = new Date("2026-09-02T06:00:00.000Z"); // 02 Sep 2026, ~11:30 IST

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(FIXED_NOW);
});
afterEach(() => vi.useRealTimers());

function note(text: string, follow_up_date: string | null, created_at = "2026-09-01T00:00:00Z"): CaseTimelineEntry {
  return { type: "note", from_status: null, to_status: null, remarks: null, text, follow_up_date, created_by: "Emp A", created_at };
}

describe("FollowUpHistory", () => {
  it("groups by the entry's own follow-up date and renders strictly Past → Today → Future → Other", () => {
    render(
      <FollowUpHistory
        entries={[
          note("future one", "2026-09-05T00:00:00Z"),
          note("undated", null),
          note("past one", "2026-08-30T00:00:00Z"),
          note("today one", "2026-09-02T00:00:00Z"),
          { type: "status", from_status: "credit_evaluation", to_status: "re_eligible", remarks: null, text: null, follow_up_date: null, created_by: null, created_at: "x" },
        ]}
      />,
    );
    const headings = screen.getAllByText(/^(Past|Today|Future|Other History)$/i).map((el) => el.textContent);
    expect(headings).toEqual(["Past", "Today", "Future", "Other History"]);
    // status entries are ignored.
    expect(screen.queryByText(/re_eligible/i)).not.toBeInTheDocument();
  });

  it("sorts within Past/Future by follow-up date ascending", () => {
    render(
      <FollowUpHistory
        entries={[
          note("p 01 Sep", "2026-09-01T00:00:00Z"),
          note("p 25 Aug", "2026-08-25T00:00:00Z"),
          note("p 30 Aug", "2026-08-30T00:00:00Z"),
        ]}
      />,
    );
    const texts = screen.getAllByText(/^p \d\d /).map((el) => el.textContent);
    expect(texts).toEqual(["p 25 Aug", "p 30 Aug", "p 01 Sep"]);
  });

  it("an undated comment goes to Other History, never mis-classified", () => {
    render(<FollowUpHistory entries={[note("no date here", null)]} />);
    const other = screen.getByText("Other History").closest("div")!.parentElement!;
    expect(within(other).getByText("no date here")).toBeInTheDocument();
    expect(screen.queryByText("Past")).not.toBeInTheDocument();
    expect(screen.queryByText("Today")).not.toBeInTheDocument();
  });

  it("empty state when there are no notes", () => {
    render(<FollowUpHistory entries={[]} />);
    expect(screen.getByText("No comments yet.")).toBeInTheDocument();
  });
});
