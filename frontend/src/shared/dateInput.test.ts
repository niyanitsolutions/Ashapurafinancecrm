import { describe, expect, it } from "vitest";
import { displayDate, parseDate } from "./dateInput";
import { formatISTDate } from "./dateFormat";

describe("calendar dates", () => {
  it("round trips without a timezone shift", () => {
    expect(displayDate("1992-09-16")).toBe("16/09/1992");
    expect(parseDate("16/09/1992")).toBe("1992-09-16");
    expect(formatISTDate("1992-09-16")).toBe("16/09/1992");
  });
  it("rejects impossible dates and accepts leap day", () => {
    expect(parseDate("31/02/2026")).toBeNull();
    expect(parseDate("29/02/2024")).toBe("2024-02-29");
    expect(parseDate("16/9/1992")).toBeNull();
  });
});
