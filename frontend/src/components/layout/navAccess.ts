// Shared "does the user have access to this nav key?" check. A leaf/tab may
// gate on a single permission-filtered nav_items key, or (for consolidated
// sidebar entries that used to be several separate leaves under different
// keys — e.g. Settings = "settings" or "reminder_rules") on any one of
// several — visible if the live nav catalog contains at least one of them.
export function hasNavAccess(availableKeys: Set<string> | undefined, matchKey: string | string[] | undefined): boolean {
  if (!matchKey) return true;
  if (!availableKeys) return false;
  return Array.isArray(matchKey) ? matchKey.some((key) => availableKeys.has(key)) : availableKeys.has(matchKey);
}
