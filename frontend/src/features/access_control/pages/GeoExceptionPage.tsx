import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { EmployeeSelect } from "@/components/forms/EmployeeSelect";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { useEmployeeNameMap } from "@/components/forms/useEmployeeNameMap";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Modal } from "@/components/overlays/Modal";
import { createGeoException, listGeoExceptions, revokeGeoException, type GeoException } from "@/features/access_control/api";
import { getErrorMessage } from "@/features/access_control/errors";
import { listGeoFences, type GeoFence } from "@/features/geo_fencing/api";

function GrantExceptionModal({
  fences,
  onClose,
  onSaved,
}: {
  fences: GeoFence[];
  onClose: () => void;
  onSaved: () => void;
}) {
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
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSelectFence = (fenceId: string) => {
    setGeoFenceId(fenceId);
    const fence = fences.find((f) => f.id === fenceId);
    if (fence) {
      setLatitude(String(fence.latitude));
      setLongitude(String(fence.longitude));
      setRadius(String(fence.radius_meters));
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
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
      onSaved();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Grant Geo Exception"
      size="lg"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="geo-exception-form" size="sm" loading={isSubmitting}>
            Grant Exception
          </Button>
        </>
      }
    >
      <form id="geo-exception-form" onSubmit={onSubmit}>
        <ErrorBanner message={error} />
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
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
          <FormField label="Start date" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} required />
          <FormField label="End date" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} required />
          <FormField label="Start time (daily)" type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} required />
          <FormField label="End time (daily)" type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} required />
        </div>
      </form>
    </Modal>
  );
}

// Enforced server-side by app/features/geo_fencing/enforcement.py for lead_creation and
// document_collection — see docs/GEO_FENCING.md. Selecting a Geo Fence in the modal
// prefills latitude/longitude/radius from it; the fields stay editable to override if needed.
export function GeoExceptionPage() {
  const employeeNames = useEmployeeNameMap();
  const [items, setItems] = useState<GeoException[]>([]);
  const [fences, setFences] = useState<GeoFence[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const load = () => {
    listGeoExceptions().then(setItems).catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);
  useEffect(() => {
    listGeoFences({ page_size: 100, status: "active" })
      .then(({ items }) => setFences(items))
      .catch(() => setFences([]));
  }, []);

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
    <SimplePageLayout
      title="Geo-fencing Exceptions"
      subtitle="Grant temporary location exceptions to individual employees."
      actions={<Button size="sm" onClick={() => setIsModalOpen(true)}>+ Grant Exception</Button>}
    >
      <ErrorBanner message={error} />

      {items.length === 0 ? (
        <EmptyState
          icon="map-pin"
          title="No geo exceptions yet"
          description="Grant a geo-fencing exception to let an employee act outside a configured fence for a limited window."
          primaryAction={{ label: "+ Grant Exception", onClick: () => setIsModalOpen(true) }}
        />
      ) : (
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
      )}

      {isModalOpen && (
        <GrantExceptionModal
          fences={fences}
          onClose={() => setIsModalOpen(false)}
          onSaved={() => {
            setIsModalOpen(false);
            load();
          }}
        />
      )}
    </SimplePageLayout>
  );
}
