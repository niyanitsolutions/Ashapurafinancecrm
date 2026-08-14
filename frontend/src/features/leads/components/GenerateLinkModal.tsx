import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { CheckboxField } from "@/components/forms/CheckboxField";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { Modal } from "@/components/overlays/Modal";
import {
  disableSecureLink,
  generateSecureLink,
  getCurrentSecureLink,
  logSecureLinkEvent,
  notifySecureLink,
  type NotifyChannel,
  type SecureLink,
} from "@/features/customer/api";
import { getErrorMessage } from "@/features/leads/errors";
import { Icon } from "@/theme/icons";

const EXPIRY_DAY_OPTIONS = [7, 15, 30] as const;

const CHANNELS: { key: NotifyChannel; label: string; icon: "chat" | "phone" | "mail" }[] = [
  { key: "whatsapp", label: "WhatsApp", icon: "chat" },
  { key: "sms", label: "SMS", icon: "phone" },
  { key: "email", label: "Email", icon: "mail" },
];

const STATUS_LABEL: Record<SecureLink["status"], string> = { active: "Active", used: "Used", revoked: "Disabled" };
const STATUS_COLOR: Record<SecureLink["status"], string> = { active: "text-success", used: "text-textSecondary", revoked: "text-danger" };

// Consolidates what used to be split across LeadDetailsPage's always-open `SecureLinkCard`
// and `features/customer/components/GenerateSecureLinkModal` into one self-contained modal
// — same real endpoints (getCurrentSecureLink/generateSecureLink/disableSecureLink/
// notifySecureLink/logSecureLinkEvent), just triggerable from the Leads table row directly
// (no navigation to the details page) or from the details page's own "Generate Link"
// button. Expiry is presented as 7/15/30-day radios (converted to `expiry_minutes` for the
// existing API, which only ever spoke minutes) rather than the old hours/days dropdown.
export function GenerateLinkModal({ leadId, leadCode, onClose }: { leadId: string; leadCode: string; onClose: () => void }) {
  const [link, setLink] = useState<SecureLink | null>(null);
  const [isLoadingLink, setIsLoadingLink] = useState(true);
  const [mode, setMode] = useState<"form" | "ready">("form");

  const [expiryDays, setExpiryDays] = useState<(typeof EXPIRY_DAY_OPTIONS)[number]>(7);
  const [oneTimeUse, setOneTimeUse] = useState(true);
  const [notifyChannels, setNotifyChannels] = useState<Set<NotifyChannel>>(new Set());
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [shareStatus, setShareStatus] = useState<Record<string, string>>({});
  const [confirmDisable, setConfirmDisable] = useState(false);
  const copiedTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    getCurrentSecureLink(leadId)
      .then((existing) => {
        setLink(existing);
        setMode(existing ? "ready" : "form");
      })
      .catch(() => setMode("form"))
      .finally(() => setIsLoadingLink(false));
  }, [leadId]);

  // Copying then closing the modal within the 2s window would otherwise call
  // `setCopied` on an unmounted component.
  useEffect(() => {
    return () => {
      if (copiedTimeoutRef.current) clearTimeout(copiedTimeoutRef.current);
    };
  }, []);

  const toggleChannel = (channel: NotifyChannel) =>
    setNotifyChannels((prev) => {
      const next = new Set(prev);
      if (next.has(channel)) next.delete(channel);
      else next.add(channel);
      return next;
    });

  const onGenerate = async () => {
    setError(null);
    setIsSubmitting(true);
    try {
      const result = await generateSecureLink(leadId, {
        expiry_minutes: expiryDays * 24 * 60,
        one_time_use: oneTimeUse,
        notify_channels: notifyChannels.size > 0 ? Array.from(notifyChannels) : undefined,
      });
      setLink(result);
      setMode("ready");
      setShareStatus({});
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const onCopy = async () => {
    if (!link) return;
    await navigator.clipboard.writeText(link.link_url);
    setCopied(true);
    logSecureLinkEvent(link.id, "secure_link_copied").catch(() => undefined);
    if (copiedTimeoutRef.current) clearTimeout(copiedTimeoutRef.current);
    copiedTimeoutRef.current = setTimeout(() => setCopied(false), 2000);
  };

  const onOpen = () => {
    if (link) window.open(link.link_url, "_blank", "noopener,noreferrer");
  };

  const onShare = async (channel: NotifyChannel) => {
    if (!link) return;
    setShareStatus((prev) => ({ ...prev, [channel]: "sending" }));
    try {
      const updated = await notifySecureLink(link.id, [channel]);
      setLink(updated);
      setShareStatus((prev) => ({ ...prev, [channel]: updated.notification_status?.[channel] ?? "sent" }));
    } catch (err) {
      setShareStatus((prev) => ({ ...prev, [channel]: "failed" }));
      setError(getErrorMessage(err));
    }
  };

  const onDisable = async () => {
    if (!link) return;
    try {
      const updated = await disableSecureLink(link.id);
      setLink(updated);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setConfirmDisable(false);
    }
  };

  const isExpired = link?.status === "active" && new Date(link.expires_at) < new Date();

  const footer =
    !isLoadingLink && mode === "form" ? (
      <>
        <Button variant="secondary" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button size="sm" loading={isSubmitting} onClick={onGenerate}>
          Generate Link
        </Button>
      </>
    ) : !isLoadingLink && link ? (
      <div className="flex w-full items-center justify-between">
        {link.status === "active" ? (
          <button type="button" onClick={() => setConfirmDisable(true)} className="text-sm font-medium text-danger hover:underline">
            Disable Link
          </button>
        ) : (
          <span />
        )}
        <Button size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
    ) : undefined;

  return (
    <>
    <Modal open onClose={onClose} title="Secure Application Link" description={`Lead ${leadCode}`} footer={footer}>
      {error && <p className="mb-3 text-sm text-danger">{error}</p>}

      {isLoadingLink ? (
        <p className="text-sm text-textSecondary py-6 text-center">Loading…</p>
      ) : mode === "form" ? (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text mb-2">Expiry</label>
            <div className="flex gap-2">
              {EXPIRY_DAY_OPTIONS.map((days) => (
                <button
                  key={days}
                  type="button"
                  onClick={() => setExpiryDays(days)}
                  className={`flex-1 rounded-xl border py-2.5 text-sm font-semibold transition-colors ${
                    expiryDays === days ? "border-primary bg-primary/10 text-primary" : "border-border text-textSecondary hover:bg-background"
                  }`}
                >
                  {days} Days
                </button>
              ))}
            </div>
          </div>

          <CheckboxField label="One-time use only" checked={oneTimeUse} onChange={() => setOneTimeUse((v) => !v)} />

          <div>
            <div className="text-sm font-medium text-text mb-2">Notify customer</div>
            <div className="flex gap-4">
              {CHANNELS.map((c) => (
                <CheckboxField
                  key={c.key}
                  label={c.label}
                  checked={notifyChannels.has(c.key)}
                  onChange={() => toggleChannel(c.key)}
                />
              ))}
            </div>
          </div>
        </div>
      ) : (
        link && (
          <>
            <div className="space-y-1.5 text-sm mb-4">
              <div className="flex justify-between">
                <span className="text-textSecondary">Status</span>
                <span className={`font-medium ${STATUS_COLOR[link.status]}`}>
                  {STATUS_LABEL[link.status]}
                  {isExpired ? " (expired)" : ""}
                </span>
              </div>
              <div className="rounded-lg border border-border bg-background px-3 py-2 text-2xs break-all text-text">{link.link_url}</div>
              <div className="flex justify-between">
                <span className="text-textSecondary">Expiry Date</span>
                <span className="text-text">{new Date(link.expires_at).toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">Created On</span>
                <span className="text-text">{new Date(link.created_at).toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">Created By</span>
                <span className="text-text">{link.created_by_name ?? "—"}</span>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" size="sm" icon={<Icon name="copy" className="h-3.5 w-3.5" />} onClick={onCopy}>
                {copied ? "Copied!" : "Copy"}
              </Button>
              <Button variant="secondary" size="sm" icon={<Icon name="link" className="h-3.5 w-3.5" />} onClick={onOpen}>
                Open
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => onShare("whatsapp")}
                disabled={shareStatus.whatsapp === "sending"}
              >
                {shareStatus.whatsapp === "sending" ? "Sending…" : "Share WhatsApp"}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => onShare("sms")} disabled={shareStatus.sms === "sending"}>
                {shareStatus.sms === "sending" ? "Sending…" : "Send SMS"}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setMode("form")}>
                Regenerate
              </Button>
            </div>
          </>
        )
      )}
    </Modal>
    <ConfirmDialog
      open={confirmDisable}
      title="Disable Secure Link"
      message="Disable this secure link? The customer will no longer be able to use it."
      confirmLabel="Disable"
      confirmVariant="danger"
      onConfirm={onDisable}
      onClose={() => setConfirmDisable(false)}
    />
    </>
  );
}
