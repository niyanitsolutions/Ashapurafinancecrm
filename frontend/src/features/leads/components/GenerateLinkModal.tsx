import { useEffect, useRef, useState } from "react";
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

function OutlineButton({ children, onClick, disabled, tone = "default" }: { children: React.ReactNode; onClick: () => void; disabled?: boolean; tone?: "default" | "danger" }) {
  const toneClass = tone === "danger" ? "text-danger border-danger/25 hover:bg-danger/5" : "text-text border-border hover:bg-background";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-1.5 rounded-lg border text-sm font-medium py-2 px-3.5 transition-colors disabled:opacity-50 ${toneClass}`}
    >
      {children}
    </button>
  );
}

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
    if (!window.confirm("Disable this secure link? The customer will no longer be able to use it.")) return;
    try {
      const updated = await disableSecureLink(link.id);
      setLink(updated);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const isExpired = link?.status === "active" && new Date(link.expires_at) < new Date();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="w-full max-w-md bg-card border border-border rounded-2xl shadow-dropdown p-6">
        <div className="flex items-center gap-2.5 mb-1">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
            <Icon name="link" className="h-4 w-4" />
          </span>
          <h2 className="text-lg font-bold text-text">Secure Application Link</h2>
        </div>
        <p className="text-2xs text-textSecondary mb-4 ml-[46px]">
          Lead <span className="font-semibold text-text">{leadCode}</span>
        </p>

        {error && <p className="mb-3 text-sm text-danger">{error}</p>}

        {isLoadingLink ? (
          <p className="text-sm text-textSecondary py-6 text-center">Loading…</p>
        ) : mode === "form" ? (
          <>
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

              <label className="flex items-center gap-2 text-sm text-text cursor-pointer">
                <input type="checkbox" checked={oneTimeUse} onChange={() => setOneTimeUse((v) => !v)} className="accent-primary" />
                One-time use only
              </label>

              <div>
                <div className="text-sm font-medium text-text mb-2">Notify customer</div>
                <div className="flex gap-4">
                  {CHANNELS.map((c) => (
                    <label key={c.key} className="flex items-center gap-1.5 text-sm text-text cursor-pointer">
                      <input type="checkbox" checked={notifyChannels.has(c.key)} onChange={() => toggleChannel(c.key)} className="accent-primary" />
                      {c.label}
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-2.5">
              <OutlineButton onClick={onClose}>Cancel</OutlineButton>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={onGenerate}
                className="hover-lift rounded-lg bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-semibold py-2 px-4 shadow-card disabled:opacity-50"
              >
                {isSubmitting ? "Generating…" : "Generate Link"}
              </button>
            </div>
          </>
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
                <OutlineButton onClick={onCopy}>
                  <Icon name="copy" className="h-3.5 w-3.5" />
                  {copied ? "Copied!" : "Copy"}
                </OutlineButton>
                <OutlineButton onClick={onOpen}>
                  <Icon name="link" className="h-3.5 w-3.5" />
                  Open
                </OutlineButton>
                <OutlineButton onClick={() => onShare("whatsapp")} disabled={shareStatus.whatsapp === "sending"}>
                  {shareStatus.whatsapp === "sending" ? "Sending…" : "Share WhatsApp"}
                </OutlineButton>
                <OutlineButton onClick={() => onShare("sms")} disabled={shareStatus.sms === "sending"}>
                  {shareStatus.sms === "sending" ? "Sending…" : "Send SMS"}
                </OutlineButton>
                <OutlineButton onClick={() => setMode("form")}>Regenerate</OutlineButton>
              </div>

              <div className="mt-6 flex items-center justify-between">
                {link.status === "active" ? (
                  <button type="button" onClick={onDisable} className="text-sm font-medium text-danger hover:underline">
                    Disable Link
                  </button>
                ) : (
                  <span />
                )}
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-lg bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-semibold py-2 px-5 shadow-card"
                >
                  Close
                </button>
              </div>
            </>
          )
        )}
      </div>
    </div>
  );
}
