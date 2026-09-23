import { describe, expect, it } from "vitest";
import { notificationDestination } from "./notificationDestination";

describe("notificationDestination", () => {
  it.each([
    ["lead", "/leads/record-1"], ["insurance_case", "/insurance-cases/record-1"],
    ["support_ticket", "/support-tickets?ticket=record-1"], ["application", "/applications/record-1"],
    ["task", "/tasks?task=record-1"],
  ])("opens the exact %s reference", (entity_type, route) => {
    expect(notificationDestination({ entity_type, entity_id: "record-1" })).toBe(route);
  });
  it("falls back safely for legacy and unknown entities", () => {
    expect(notificationDestination({ entity_type: null, entity_id: null })).toBe("/notifications");
    expect(notificationDestination({ entity_type: "external", entity_id: "https://evil.example" })).toBe("/notifications");
    expect(notificationDestination({ entity_type: "lead", entity_id: "1" }, "customer")).toBe("/portal/alerts");
  });
  it("encodes entity IDs rather than trusting a URL", () => {
    expect(notificationDestination({ entity_type: "lead", entity_id: "a/b?x=1" })).toBe("/leads/a%2Fb%3Fx%3D1");
  });
});
