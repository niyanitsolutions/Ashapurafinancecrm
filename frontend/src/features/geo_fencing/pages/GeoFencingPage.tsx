import { useEffect, useState } from "react";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
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

  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [isSubmitting, setIsSubmitting] = useState(false);

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

  const resetForm = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
  };

  const startEdit = (fence: GeoFence) => {
    setEditingId(fence.id);
    setForm({
      area_name: fence.area_name, address: fence.address, latitude: String(fence.latitude),
      longitude: String(fence.longitude), radius_meters: String(fence.radius_meters), allowed_activities: fence.allowed_activities,
    });
  };

  const toggleActivity = (value: string) => {
    setForm((f) => ({
      ...f,
      allowed_activities: f.allowed_activities.includes(value) ? f.allowed_activities.filter((a) => a !== value) : [...f.allowed_activities, value],
    }));
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setWarning(null);
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
      const saved = editingId ? await updateGeoFence(editingId, payload) : await createGeoFence(payload);
      if (saved.overlaps_with.length > 0) {
        setWarning(`This fence overlaps with: ${saved.overlaps_with.join(", ")}. Both remain active — review if unintended.`);
      }
      resetForm();
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
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
    <SimplePageLayout title="Geo Fencing">
      <ErrorBanner message={error} />
      {warning && <div className="mb-4 rounded-xl border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">{warning}</div>}

      <form onSubmit={onSubmit} className="max-w-2xl bg-card border border-border rounded-card shadow-card p-6 mb-6">
        <h2 className="text-sm font-semibold text-text/70 mb-3">{editingId ? "Edit Geo Fence" : "Add Geo Fence"}</h2>
        <div className="grid grid-cols-2 gap-x-4">
          <FormField label="Area Name" value={form.area_name} onChange={(e) => setForm({ ...form, area_name: e.target.value })} required />
          <FormField label="Address / Location" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} required />
          <FormField
            label="Latitude" type="number" step="any" value={form.latitude}
            onChange={(e) => setForm({ ...form, latitude: e.target.value })} required
          />
          <FormField
            label="Longitude" type="number" step="any" value={form.longitude}
            onChange={(e) => setForm({ ...form, longitude: e.target.value })} required
          />
          <FormField
            label="Radius (meters)" type="number" min="1" value={form.radius_meters}
            onChange={(e) => setForm({ ...form, radius_meters: e.target.value })} required
          />
        </div>

        <fieldset className="mb-4">
          <legend className="block text-sm font-medium text-text mb-1.5">Allowed Activities</legend>
          <div className="grid grid-cols-2 gap-2">
            {GEO_ACTIVITIES.map((activity) => (
              <label key={activity.value} className="flex items-center gap-2 text-sm text-text">
                <input
                  type="checkbox"
                  checked={form.allowed_activities.includes(activity.value)}
                  onChange={() => toggleActivity(activity.value)}
                />
                {activity.label}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="flex gap-3">
          <SubmitButton isSubmitting={isSubmitting}>{editingId ? "Save Changes" : "Save"}</SubmitButton>
          {editingId && (
            <button type="button" onClick={resetForm} className="text-text/60 hover:underline text-sm">
              Cancel
            </button>
          )}
        </div>
      </form>

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
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-text/50">
                  No geo fences yet.
                </td>
              </tr>
            )}
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
                  <button type="button" className="text-primary hover:underline" onClick={() => startEdit(fence)}>
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

      <Pagination page={page} totalPages={totalPages} totalItems={total} pageSize={pageSize} itemLabel="geo fences" onPageChange={setPage} onPageSizeChange={(size) => { setPage(1); setPageSize(size); }} />
    </SimplePageLayout>
  );
}
