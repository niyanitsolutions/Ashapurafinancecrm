import { useEffect, useState } from "react";
import { EmployeeSelect } from "@/components/forms/EmployeeSelect";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { useEmployeeNameMap } from "@/components/forms/useEmployeeNameMap";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { createGeoException, listGeoExceptions, revokeGeoException, type GeoException } from "@/features/access_control/api";
import { getErrorMessage } from "@/features/access_control/errors";
import { listGeoFences, type GeoFence } from "@/features/geo_fencing/api";

// Enforced server-side by app/features/geo_fencing/enforcement.py for lead_creation and
// document_collection — see docs/GEO_FENCING.md. Selecting a Geo Fence below prefills
// latitude/longitude/radius from it; the fields stay editable to override if needed.
export function GeoExceptionPage() {
  const employeeNames = useEmployeeNameMap();
  const [items, setItems] = useState<GeoException[]>([]);
  const [fences, setFences] = useState<GeoFence[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [employeeId, setEmployeeId] = useState("");
  const [geoFenceId, setGeoFenceId] = useState("");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [radius, setRadius] = useState("500");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [startTime, setStartTime] = useState("09:00");
  const [endTime, setEndTime] = useState("18:00");
  const [reason, setReason] = useState("");

  const load = () => {
    listGeoExceptions().then(setItems).catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);
  useEffect(() => {
    listGeoFences({ page_size: 100, status: "active" })
      .then(({ items }) => setFences(items))
      .catch(() => setFences([]));
  }, []);

  const onSelectFence = (fenceId: string) => {
    setGeoFenceId(fenceId);
    const fence = fences.find((f) => f.id === fenceId);
    if (fence) {
      setLatitude(String(fence.latitude));
      setLongitude(String(fence.longitude));
      setRadius(String(fence.radius_meters));
    }
  };

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await createGeoException({
        employee_id: employeeId,
        geo_fence_id: geoFenceId || undefined,
        latitude: latitude ? Number(latitude) : undefined,
        longitude: longitude ? Number(longitude) : undefined,
        radius_meters: radius ? Number(radius) : undefined,
        start_date: startDate,
        end_date: endDate,
        start_time: startTime,
        end_time: endTime,
        reason,
      });
      setEmployeeId("");
      setGeoFenceId("");
      setReason("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onRevoke = async (id: string) => {
    setError(null);
    try {
      await revokeGeoException(id);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="Geo-fencing Exceptions">
      <ErrorBanner message={error} />

      <form onSubmit={onCreate} className="max-w-2xl bg-card border border-border rounded-card shadow-card p-6 mb-6">
        <h2 className="text-sm font-semibold text-text/70 mb-3">Grant Geo Exception</h2>
        <div className="grid grid-cols-2 gap-x-4">
          <EmployeeSelect label="Employee" value={employeeId} onChange={setEmployeeId} required />
          <SelectField
            label="Geo Fence (optional)"
            placeholder="None — enter coordinates manually"
            value={geoFenceId}
            onChange={(e) => onSelectFence(e.target.value)}
            options={fences.map((f) => ({ value: f.id, label: f.area_name }))}
          />
          <FormField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} required />
          <FormField label="Latitude" value={latitude} onChange={(e) => setLatitude(e.target.value)} required={!geoFenceId} />
          <FormField label="Longitude" value={longitude} onChange={(e) => setLongitude(e.target.value)} required={!geoFenceId} />
          <FormField label="Radius (meters)" type="number" value={radius} onChange={(e) => setRadius(e.target.value)} required={!geoFenceId} />
          <div />
          <FormField label="Start date" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} required />
          <FormField label="End date" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} required />
          <FormField label="Start time (daily)" type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} required />
          <FormField label="End time (daily)" type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} required />
        </div>
        <SubmitButton>Grant Exception</SubmitButton>
      </form>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Employee</th>
              <th className="px-4 py-3">Location</th>
              <th className="px-4 py-3">Window</th>
              <th className="px-4 py-3">Reason</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-text/50">
                  No geo exceptions.
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-b border-border last:border-0">
                <td className="px-4 py-3">{employeeNames[item.employee_id] ?? item.employee_id}</td>
                <td className="px-4 py-3">
                  {item.latitude.toFixed(4)}, {item.longitude.toFixed(4)} (±{item.radius_meters}m)
                </td>
                <td className="px-4 py-3">
                  {item.start_date} → {item.end_date}, {item.start_time}–{item.end_time}
                </td>
                <td className="px-4 py-3">{item.reason}</td>
                <td className="px-4 py-3 capitalize">{item.status}</td>
                <td className="px-4 py-3">
                  {item.status === "active" && (
                    <button type="button" onClick={() => onRevoke(item.id)} className="text-danger hover:underline text-xs">
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SimplePageLayout>
  );
}
