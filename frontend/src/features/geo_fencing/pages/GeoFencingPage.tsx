import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { CheckboxField } from "@/components/forms/CheckboxField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Modal } from "@/components/overlays/Modal";
import { Pagination } from "@/components/tables/Pagination";
import {
  GEO_ACTIVITIES,
  activateGeoFence,
  createGeoFence,
  deactivateGeoFence,
  deleteGeoFence,
  listGeoFences,
  updateGeoFence,
  type GeoFence,
} from "@/features/geo_fencing/api";
import { getErrorMessage } from "@/shared/api/errors";

const EMPTY_FORM = { area_name: "", address: "", latitude: "", longitude: "", radius_meters: "", allowed_activities: [] as string[] };

function GeoFenceFormModal({
  fence,
  onClose,
  onSaved,
}: {
  fence: GeoFence | null;
  onClose: () => void;
  onSaved: (saved: GeoFence) => void;
}) {
  const [form, setForm] = useState(() =>
    fence
      ? {
          area_name: fence.area_name, address: fence.address, latitude: String(fence.latitude),
          longitude: String(fence.longitude), radius_meters: String(fence.radius_meters), allowed_activities: fence.allowed_activities,
        }
      : EMPTY_FORM,
  );
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const toggleActivity = (value: string) => {
    setForm((f) => ({
      ...f,
      allowed_activities: f.allowed_activities.includes(value) ? f.allowed_activities.filter((a) => a !== value) : [...f.allowed_activities, value],
    }));
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const payload = {
        area_name: form.area_name,
        address: form.address,
        latitude: Number(form.latitude),
        longitude: Number(form.longitude),
        radius_meters: Number(form.radius_meters),
        allowed_activities: form.allowed_activities,
      };
      const saved = fence ? await updateGeoFence(fence.id, payload) : await createGeoFence(payload);
      onSaved(saved);
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
      title={fence ? "Edit Geo Fence" : "Add Geo Fence"}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="geo-fence-form" size="sm" loading={isSubmitting}>
            {fence ? "Save Changes" : "Save"}
          </Button>
        </>
      }
    >
      <form id="geo-fence-form" onSubmit={onSubmit}>
        <ErrorBanner message={error} />
        <FormField label="Area Name" value={form.area_name} onChange={(e) => setForm({ ...form, area_name: e.target.value })} required />
        <FormField label="Address / Location" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} required />
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <FormField
            label="Latitude" type="number" step="any" value={form.latitude}
            onChange={(e) => setForm({ ...form, latitude: e.target.value })} required
          />
          <FormField
            label="Longitude" type="number" step="any" value={form.longitude}
            onChange={(e) => setForm({ ...form, longitude: e.target.value })} required
          />
        </div>
        <FormField
          label="Radius (meters)" type="number" min="1" value={form.radius_meters}
          onChange={(e) => setForm({ ...form, radius_meters: e.target.value })} required
        />

        <fieldset className="mb-2">
          <legend className="mb-1.5 block text-sm font-medium text-text">Allowed Activities</legend>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {GEO_ACTIVITIES.map((activity) => (
              <CheckboxField
                key={activity.value}
                label={activity.label}
                checked={form.allowed_activities.includes(activity.value)}
                onChange={() => toggleActivity(activity.value)}
              />
            ))}
          </div>
        </fieldset>
      </form>
    </Modal>
  );
}

export function GeoFencingPage() {
  const [items, setItems] = useState<GeoFence[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState("");
  const [activityFilter, setActivityFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [modalFence, setModalFence] = useState<GeoFence | null | "new">(null);

  const load = () => {
    listGeoFences({ page, page_size: pageSize, search: search || undefined, activity: activityFilter || undefined, status: statusFilter || undefined })
      .then(({ items, pagination }) => {
        setItems(items);
        setTotal(pagination?.total ?? items.length);
        setTotalPages(pagination?.total_pages ?? 1);
      })
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, [page, pageSize, search, activityFilter, statusFilter]);

  const onSaved = (saved: GeoFence) => {
    setModalFence(null);
    setWarning(saved.overlaps_with.length > 0 ? `This fence overlaps with: ${saved.overlaps_with.join(", ")}. Both remain active — review if unintended.` : null);
    load();
  };

  const onToggleStatus = async (fence: GeoFence) => {
    setError(null);
    try {
      await (fence.status === "active" ? deactivateGeoFence(fence.id) : activateGeoFence(fence.id));
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onDelete = async (fence: GeoFence) => {
    setError(null);
    try {
      await deleteGeoFence(fence.id);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout
      title="Geo Fencing"
      subtitle="Configure location-based activity controls."
      actions={<Button size="sm" onClick={() => setModalFence("new")}>+ Add Geo Fence</Button>}
    >
      <ErrorBanner message={error} />
      {warning && <div className="mb-4 rounded-xl border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">{warning}</div>}

      <div className="flex flex-wrap gap-3 mb-4 max-w-2xl">
        <FormField label="Search" placeholder="Area name or address" value={search} onChange={(e) => { setPage(1); setSearch(e.target.value); }} />
        <SelectField
          label="Activity" placeholder="All activities" value={activityFilter}
          onChange={(e) => { setPage(1); setActivityFilter(e.target.value); }}
          options={GEO_ACTIVITIES.map((a) => ({ value: a.value, label: a.label }))}
        />
        <SelectField
          label="Status" placeholder="All statuses" value={statusFilter}
          onChange={(e) => { setPage(1); setStatusFilter(e.target.value); }}
          options={[{ value: "active", label: "Active" }, { value: "inactive", label: "Inactive" }]}
        />
      </div>

      {items.length === 0 ? (
        <EmptyState
          icon="map-pin"
          title="No Geo Fences yet"
          description="Create your first geo fence to control location-based activities."
          primaryAction={{ label: "+ Add Geo Fence", onClick: () => setModalFence("new") }}
        />
      ) : (
        <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text/60">
                <th className="px-4 py-3">Area Name</th>
                <th className="px-4 py-3">Location</th>
                <th className="px-4 py-3">Radius</th>
                <th className="px-4 py-3">Activities</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.map((fence) => (
                <tr key={fence.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3">{fence.area_name}</td>
                  <td className="px-4 py-3">{fence.address}</td>
                  <td className="px-4 py-3">{(fence.radius_meters / 1000).toFixed(fence.radius_meters % 1000 === 0 ? 0 : 1)} KM</td>
                  <td className="px-4 py-3 text-xs text-text/60">
                    {fence.allowed_activities.map((a) => GEO_ACTIVITIES.find((x) => x.value === a)?.label ?? a).join(", ") || "—"}
                  </td>
                  <td className="px-4 py-3 capitalize">{fence.status}</td>
                  <td className="px-4 py-3 text-right space-x-3">
                    <button type="button" className="text-primary hover:underline" onClick={() => setModalFence(fence)}>
                      Edit
                    </button>
                    <button type="button" className="text-text/60 hover:underline" onClick={() => onToggleStatus(fence)}>
                      {fence.status === "active" ? "Deactivate" : "Activate"}
                    </button>
                    <button type="button" className="text-danger hover:underline" onClick={() => onDelete(fence)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Pagination page={page} totalPages={totalPages} totalItems={total} pageSize={pageSize} itemLabel="geo fences" onPageChange={setPage} onPageSizeChange={(size) => { setPage(1); setPageSize(size); }} />

      {modalFence && (
        <GeoFenceFormModal fence={modalFence === "new" ? null : modalFence} onClose={() => setModalFence(null)} onSaved={onSaved} />
      )}
    </SimplePageLayout>
  );
}
