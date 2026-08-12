import { Card, CardHeader } from "@/components/cards/Card";
import { NoDataState } from "@/components/charts/NoDataState";
import { Icon } from "@/theme/icons";

// The reference's "Leads Overview" is a weekly Total/Assigned/Converted trend line — no
// backend widget computes leads over time (only point-in-time counts and a 6-month
// *revenue* trend exist; see the dashboard redesign notes). Rather than fabricate a
// series, this is an honest "No data available" until a real leads-over-time widget
// exists — same policy as every other real gap on this dashboard.
export function LeadsOverviewCard() {
  return (
    <Card>
      <CardHeader
        title="Leads Overview"
        subtitle="Total, assigned & converted"
        icon={
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0">
            <Icon name="leads" className="h-4 w-4" />
          </span>
        }
      />
      <NoDataState icon="leads" message="No trend data available yet" />
    </Card>
  );
}
