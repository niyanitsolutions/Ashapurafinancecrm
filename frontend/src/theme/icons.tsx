import type { ReactNode, SVGProps } from "react";

// Reserved slot (see decision history) — now filled in for the sidebar/header redesign.
// Deliberately primitive-based (circle/rect/line/polyline), not freehand bezier paths,
// so every icon renders correctly without depending on a third-party icon library.
export type IconName =
  | "dashboard"
  | "leads"
  | "customers"
  | "applications"
  | "tasks"
  | "documents"
  | "loan"
  | "insurance"
  | "re-eligible"
  | "referral"
  | "commission"
  | "reports"
  | "communication"
  | "lead-capture"
  | "integrations"
  | "employees"
  | "roles"
  | "departments"
  | "settings"
  | "shield-check"
  | "map-pin"
  | "search"
  | "bell"
  | "plus"
  | "chat"
  | "user"
  | "chevron-left"
  | "chevron-right"
  | "chevron-down"
  | "logout"
  | "menu"
  | "clock"
  | "grid"
  | "check-circle"
  | "x-circle"
  | "alert-triangle"
  | "phone"
  | "mail"
  | "upload"
  | "eye"
  | "eye-off"
  | "filter"
  | "calendar"
  | "trending-up"
  | "trending-down"
  | "chevron-up"
  | "funnel"
  | "edit"
  | "trash"
  | "download"
  | "link"
  | "print"
  | "copy"
  | "close";

const ICONS: Record<IconName, ReactNode> = {
  dashboard: (
    <>
      <rect x="3" y="3" width="7.5" height="9" rx="1.5" />
      <rect x="13.5" y="3" width="7.5" height="5" rx="1.5" />
      <rect x="13.5" y="10.5" width="7.5" height="10.5" rx="1.5" />
      <rect x="3" y="14.5" width="7.5" height="6.5" rx="1.5" />
    </>
  ),
  leads: (
    <>
      <circle cx="9" cy="7.5" r="3.25" />
      <path d="M2.75 20.5c0-3.87 2.8-7 6.25-7s6.25 3.13 6.25 7" />
      <circle cx="17" cy="8.5" r="2.25" />
      <path d="M15 13.3c2.4.55 4.25 2.85 4.25 5.7" />
    </>
  ),
  customers: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20.5c0-4.4 3.6-8 8-8s8 3.6 8 8" />
    </>
  ),
  applications: (
    <>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <line x1="8" y1="8" x2="16" y2="8" />
      <line x1="8" y1="12" x2="16" y2="12" />
      <line x1="8" y1="16" x2="13" y2="16" />
    </>
  ),
  tasks: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <polyline points="8,12 11,15 16,9" />
    </>
  ),
  documents: (
    <>
      <path d="M7 3h7l4 4v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
      <polyline points="14,3 14,7 18,7" />
      <line x1="9" y1="13" x2="15" y2="13" />
      <line x1="9" y1="17" x2="15" y2="17" />
    </>
  ),
  loan: (
    <>
      <circle cx="12" cy="12" r="9" />
      <line x1="12" y1="7" x2="12" y2="17" />
      <line x1="9" y1="9.5" x2="15" y2="9.5" />
      <line x1="9" y1="14.5" x2="15" y2="14.5" />
    </>
  ),
  insurance: (
    <>
      <path d="M12 2.5 20 6v6c0 5-3.4 8.7-8 9.5-4.6-.8-8-4.5-8-9.5V6l8-3.5Z" />
      <polyline points="9,12 11,14 15,9.5" />
    </>
  ),
  "re-eligible": (
    <>
      <path d="M4 4v6h6" />
      <path d="M20 20v-6h-6" />
      <path d="M5.2 15A8 8 0 0 0 19 9.5" />
      <path d="M18.8 9A8 8 0 0 0 5 14.5" />
    </>
  ),
  referral: (
    <>
      <circle cx="6" cy="12" r="2.75" />
      <circle cx="18" cy="6" r="2.75" />
      <circle cx="18" cy="18" r="2.75" />
      <line x1="8.4" y1="10.8" x2="15.6" y2="7.2" />
      <line x1="8.4" y1="13.2" x2="15.6" y2="16.8" />
    </>
  ),
  commission: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9.3c0-1.1 1.1-2 2.5-2s2.5.9 2.5 2-1.1 1.6-2.5 1.7c-1.4.1-2.5.7-2.5 1.9s1.1 2 2.5 2 2.5-.9 2.5-2" />
      <line x1="12" y1="6.5" x2="12" y2="17.5" />
    </>
  ),
  reports: (
    <>
      <line x1="5" y1="20" x2="5" y2="11" />
      <line x1="12" y1="20" x2="12" y2="5" />
      <line x1="19" y1="20" x2="19" y2="14" />
      <line x1="3" y1="20" x2="21" y2="20" />
    </>
  ),
  communication: (
    <>
      <path d="M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9l-5 4V6a1 1 0 0 1 1-1Z" />
      <line x1="7.5" y1="9.5" x2="16.5" y2="9.5" />
      <line x1="7.5" y1="13" x2="13.5" y2="13" />
    </>
  ),
  "lead-capture": (
    <>
      <path d="M4 4h16v9H4Z" />
      <polyline points="4,13 9,13 10.5,16 13.5,16 15,13 20,13" />
      <path d="M4 13 4 19a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-6" />
    </>
  ),
  integrations: (
    <>
      <rect x="7" y="2" width="4" height="6" rx="1" />
      <rect x="13" y="16" width="4" height="6" rx="1" />
      <path d="M9 8v3a4 4 0 0 0 4 4h2" />
      <path d="M15 8v2" />
    </>
  ),
  employees: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3 20c0-3.5 2.7-6.3 6-6.3s6 2.8 6 6.3" />
      <circle cx="17.5" cy="8.5" r="2.1" />
      <path d="M15.8 13.9c2.2.6 3.9 2.8 3.9 5.4" />
    </>
  ),
  roles: (
    <>
      <circle cx="8.5" cy="8.5" r="4.5" />
      <line x1="11.8" y1="11.8" x2="20.5" y2="20.5" />
      <line x1="16.5" y1="16" x2="19" y2="13.5" />
    </>
  ),
  departments: (
    <>
      <path d="M4 21V9l8-5 8 5v12" />
      <line x1="9" y1="21" x2="9" y2="14" />
      <line x1="15" y1="21" x2="15" y2="14" />
      <line x1="4" y1="21" x2="20" y2="21" />
    </>
  ),
  settings: (
    <>
      <line x1="5" y1="6" x2="19" y2="6" />
      <line x1="5" y1="12" x2="19" y2="12" />
      <line x1="5" y1="18" x2="19" y2="18" />
      <circle cx="9" cy="6" r="1.75" />
      <circle cx="15" cy="12" r="1.75" />
      <circle cx="9" cy="18" r="1.75" />
    </>
  ),
  "shield-check": (
    <>
      <path d="M12 2.5 20 6v6c0 5-3.4 8.7-8 9.5-4.6-.8-8-4.5-8-9.5V6l8-3.5Z" />
      <polyline points="9,12 11,14 15,9.5" />
    </>
  ),
  "map-pin": (
    <>
      <path d="M12 21s7-6.4 7-11.5A7 7 0 0 0 5 9.5C5 14.6 12 21 12 21Z" />
      <circle cx="12" cy="9.5" r="2.25" />
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <line x1="15.3" y1="15.3" x2="20.5" y2="20.5" />
    </>
  ),
  bell: (
    <>
      <path d="M6 10a6 6 0 0 1 12 0c0 4 1.5 5.5 1.5 5.5h-15S6 14 6 10Z" />
      <path d="M10 19a2 2 0 0 0 4 0" />
    </>
  ),
  plus: (
    <>
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </>
  ),
  chat: (
    <>
      <path d="M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9l-5 4V6a1 1 0 0 1 1-1Z" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20.5c0-4.4 3.6-8 8-8s8 3.6 8 8" />
    </>
  ),
  "chevron-left": <polyline points="15,5 8,12 15,19" />,
  "chevron-right": <polyline points="9,5 16,12 9,19" />,
  "chevron-down": <polyline points="5,9 12,16 19,9" />,
  logout: (
    <>
      <path d="M9 21H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h4" />
      <polyline points="15,17 20,12 15,7" />
      <line x1="20" y1="12" x2="9" y2="12" />
    </>
  ),
  menu: (
    <>
      <line x1="4" y1="6" x2="20" y2="6" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="18" x2="20" y2="18" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <polyline points="12,7 12,12 16,14" />
    </>
  ),
  grid: (
    <>
      <rect x="3" y="3" width="8" height="8" rx="1.5" />
      <rect x="13" y="3" width="8" height="8" rx="1.5" />
      <rect x="3" y="13" width="8" height="8" rx="1.5" />
      <rect x="13" y="13" width="8" height="8" rx="1.5" />
    </>
  ),
  "check-circle": (
    <>
      <circle cx="12" cy="12" r="9" />
      <polyline points="8,12.5 10.5,15 16,9" />
    </>
  ),
  "x-circle": (
    <>
      <circle cx="12" cy="12" r="9" />
      <line x1="9" y1="9" x2="15" y2="15" />
      <line x1="15" y1="9" x2="9" y2="15" />
    </>
  ),
  "alert-triangle": (
    <>
      <path d="M12 3.5 21.5 20h-19L12 3.5Z" />
      <line x1="12" y1="9.5" x2="12" y2="14" />
      <circle cx="12" cy="17" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  phone: (
    <path d="M6.5 3.5h3l1.5 4-2 1.5a11 11 0 0 0 5.5 5.5l1.5-2 4 1.5v3a1.5 1.5 0 0 1-1.6 1.5A16 16 0 0 1 5 5.1a1.5 1.5 0 0 1 1.5-1.6Z" />
  ),
  mail: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <polyline points="3,7 12,13 21,7" />
    </>
  ),
  upload: (
    <>
      <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
      <polyline points="7.5,9 12,4.5 16.5,9" />
      <line x1="12" y1="4.5" x2="12" y2="15.5" />
    </>
  ),
  eye: (
    <>
      <path d="M2 12S5.5 5 12 5s10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3.25" />
    </>
  ),
  "eye-off": (
    <>
      <path d="M9.9 4.6A10.6 10.6 0 0 1 12 4.4c6.5 0 10 6.6 10 6.6a17.3 17.3 0 0 1-3.9 4.7M6.3 6.6C3.6 8.4 2 11 2 11s3.5 6.6 10 6.6c1.3 0 2.5-.2 3.5-.6" />
      <path d="M9.9 12.7a2.75 2.75 0 0 0 3.9 3.9" />
      <line x1="3" y1="3" x2="21" y2="21" />
    </>
  ),
  filter: <path d="M4 5h16l-6 7.5V19l-4 2v-8.5Z" />,
  calendar: (
    <>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
      <line x1="3.5" y1="9.5" x2="20.5" y2="9.5" />
      <line x1="8" y1="3" x2="8" y2="6.5" />
      <line x1="16" y1="3" x2="16" y2="6.5" />
    </>
  ),
  "trending-up": (
    <>
      <polyline points="3,17 10,10 14,14 21,6" />
      <polyline points="15,6 21,6 21,12" />
    </>
  ),
  "trending-down": (
    <>
      <polyline points="3,7 10,14 14,10 21,18" />
      <polyline points="15,18 21,18 21,12" />
    </>
  ),
  "chevron-up": <polyline points="5,15 12,8 19,15" />,
  funnel: (
    <>
      <path d="M3.5 4.5h17L14 12.5v6l-4 2v-8Z" />
    </>
  ),
  edit: (
    <>
      <path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3Z" />
      <line x1="14" y1="7" x2="17.5" y2="10.5" />
    </>
  ),
  trash: (
    <>
      <line x1="4" y1="7" x2="20" y2="7" />
      <path d="M6.5 7 7.5 20a1.5 1.5 0 0 0 1.5 1.5h6a1.5 1.5 0 0 0 1.5-1.5L17.5 7" />
      <path d="M9.5 7V4.5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1V7" />
      <line x1="10.5" y1="11" x2="10.5" y2="17" />
      <line x1="13.5" y1="11" x2="13.5" y2="17" />
    </>
  ),
  download: (
    <>
      <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
      <polyline points="7.5,11.5 12,16 16.5,11.5" />
      <line x1="12" y1="16" x2="12" y2="4.5" />
    </>
  ),
  link: (
    <>
      <path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1.5 1.5" />
      <path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1.5-1.5" />
    </>
  ),
  print: (
    <>
      <rect x="5" y="8.5" width="14" height="7" rx="1.5" />
      <path d="M7 8.5V4.5a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v4" />
      <path d="M7 15v4a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-4" />
      <circle cx="16" cy="11" r="0.6" fill="currentColor" stroke="none" />
    </>
  ),
  copy: (
    <>
      <rect x="8.5" y="8.5" width="11" height="11" rx="1.5" />
      <path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5" />
    </>
  ),
  close: (
    <>
      <line x1="6" y1="6" x2="18" y2="18" />
      <line x1="18" y1="6" x2="6" y2="18" />
    </>
  ),
};

export function Icon({ name, className = "h-5 w-5", ...props }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      {...props}
    >
      {ICONS[name]}
    </svg>
  );
}
