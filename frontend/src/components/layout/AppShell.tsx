import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";

const COLLAPSE_STORAGE_KEY = "afs-crm-sidebar-collapsed";

// The real shell (Module 5 — Dashboard Framework), replacing the Foundation-era
// placeholder. Wraps every authenticated route (`<Outlet/>`) — existing pages (Employee,
// Roles, Settings, ...) keep rendering their own SimplePageLayout content inside it, so
// this only adds chrome around them, it doesn't touch a single frozen page component.
// Sidebar collapse state lives here (not inside Sidebar) since the content margin below
// needs to react to it too.
export function AppShell() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(() => localStorage.getItem(COLLAPSE_STORAGE_KEY) === "1");

  useEffect(() => {
    localStorage.setItem(COLLAPSE_STORAGE_KEY, isCollapsed ? "1" : "0");
  }, [isCollapsed]);

  return (
    <div className="min-h-screen bg-background">
      <Sidebar
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        isCollapsed={isCollapsed}
        onToggleCollapsed={() => setIsCollapsed((v) => !v)}
      />
      <div className={`transition-[margin] duration-200 ${isCollapsed ? "lg:ml-[76px]" : "lg:ml-[280px]"}`}>
        <Topbar onMenuClick={() => setIsSidebarOpen(true)} />
        <main>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
