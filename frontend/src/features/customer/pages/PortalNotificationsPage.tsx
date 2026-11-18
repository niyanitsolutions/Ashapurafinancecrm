import { NotificationListPage } from "@/features/reminders/pages/NotificationListPage";
import { Link } from "react-router-dom";

export function PortalNotificationsPage() {
  return <div className="portal-notifications"><NotificationListPage />
    <Link className="portal-back mt-6" to="/portal/notifications">View SMS and email delivery history</Link>
  </div>;
}
