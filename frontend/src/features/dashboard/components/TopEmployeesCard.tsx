import { Card, CardHeader } from "@/components/cards/Card";
import { NoDataState } from "@/components/charts/NoDataState";
import { Table, TableBody, TableHead, TableHeadRow, TableRow, Td, Th } from "@/components/tables/DataTable";
import type { Widget } from "@/features/dashboard/api";
import { widgetData } from "@/features/dashboard/useDashboardWidgets";
import { Icon } from "@/theme/icons";

// employee_performance_chart only carries one real metric per employee (closed-case
// count) — the reference's second column (a separate "Disbursed ₹" figure per employee)
// isn't computed anywhere, so this table stays two real columns rather than duplicating
// the count into a second, misleadingly-labeled column.
export function TopEmployeesCard({ widgets }: { widgets: Widget[] | undefined }) {
  const data = widgetData(widgets, "employee_performance_chart");
  const items = Array.isArray(data?.items) ? (data!.items as { label: string; value: number }[]) : [];

  return (
    <Card className="p-0 overflow-hidden xl:col-span-1">
      <div className="p-6 pb-0">
        <CardHeader
          title="Top Performing Employees"
          subtitle="By closed cases"
          icon={
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0">
              <Icon name="employees" className="h-4 w-4" />
            </span>
          }
        />
      </div>
      {items.length === 0 ? (
        <div className="px-6 pb-6">
          <NoDataState icon="employees" />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHead>
              <TableHeadRow>
                <Th>#</Th>
                <Th>Employee</Th>
                <Th>Closed Cases</Th>
              </TableHeadRow>
            </TableHead>
            <TableBody>
              {items.map((row, i) => (
                <TableRow key={row.label}>
                  <Td className="text-textSecondary">{i + 1}</Td>
                  <Td>
                    <div className="flex items-center gap-2.5">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-2xs font-semibold text-primary">
                        {row.label.slice(0, 1).toUpperCase()}
                      </span>
                      <span className="text-text font-medium truncate">{row.label}</span>
                    </div>
                  </Td>
                  <Td className="font-semibold text-text tabular-nums">{row.value.toLocaleString("en-IN")}</Td>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </Card>
  );
}
