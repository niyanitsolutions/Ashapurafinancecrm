import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { Modal } from "@/components/overlays/Modal";
import { TextareaField } from "@/components/forms/TextareaField";
import { getTimeline, setFollowUp, type TimelineEntry } from "@/features/leads/api";
import { getErrorMessage } from "@/features/leads/errors";
import { formatISTDateTime, istDateKey, todayISTDateString } from "@/shared/dateFormat";

// Shared by Fresh Leads' "Follow Up" action and My Leads' own Follow Up action (spec
// sections 6/7/12) — sets `next_follow_up_date` and, if a comment is entered, adds a
// NEW Comment History entry (LeadNote) without ever overwriting a prior one. The
// comment field always clears after a successful save so the same modal can log a
// second follow-up immediately (decision 125).
export function FollowUpModal({
  leadId,
  leadCode,
  currentFollowUpDate,
  onClose,
  onSaved,
}: {
  leadId: string;
  leadCode: string;
  currentFollowUpDate: string | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [date, setDate] = useState(currentFollowUpDate ? istDateKey(currentFollowUpDate) : todayISTDateString());
  const [comment, setComment] = useState("");
  const [notes, setNotes] = useState<TimelineEntry[]>([]);
  const [isLoadingNotes, setIsLoadingNotes] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const loadNotes = () => {
    setIsLoadingNotes(true);
    getTimeline(leadId)
      .then((entries) => setNotes(entries.filter((e) => e.type === "note")))
      .catch(() => setNotes([]))
      .finally(() => setIsLoadingNotes(false));
  };

  useEffect(loadNotes, [leadId]);

  const onSave = async () => {
    if (!date) return;
    setError(null);
    setSavedMessage(null);
    setIsSaving(true);
    try {
      await setFollowUp(leadId, date, comment.trim() || undefined);
      setComment("");
      setSavedMessage("Follow-up saved.");
      loadNotes();
      onSaved();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Follow Up"
      description={`Lead ${leadCode}`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
          <Button size="sm" loading={isSaving} disabled={!date} onClick={onSave}>
            Save Update
          </Button>
        </>
      }
    >
      {error && <p className="mb-3 text-sm text-danger">{error}</p>}
      {savedMessage && <p className="mb-3 text-sm text-success">{savedMessage}</p>}

      <div className="mb-4">
        <label className="mb-1.5 block text-sm font-medium text-text">Next Follow Up Date</label>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>

      <TextareaField
        label="Comment"
        rows={3}
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="e.g. Customer requested a call tomorrow."
      />

      <div className="mt-4">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-textSecondary">Comment History</h4>
        {isLoadingNotes ? (
          <p className="text-sm text-text/40">Loading…</p>
        ) : notes.length === 0 ? (
          <p className="text-sm text-text/40">No comments yet.</p>
        ) : (
          <div className="max-h-56 space-y-2 overflow-y-auto">
            {notes.map((note, i) => (
              <div key={i} className="rounded-lg border border-border bg-background px-3 py-2">
                <div className="text-sm text-text">{note.text}</div>
                <div className="mt-0.5 text-2xs text-textSecondary">{formatISTDateTime(note.created_at)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Modal>
  );
}
