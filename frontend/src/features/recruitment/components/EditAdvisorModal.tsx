import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { Modal } from "@/components/overlays/Modal";
import { updateAdvisor, type AdvisorDetail } from "@/features/recruitment/api";
import { getErrorMessage } from "@/shared/api/errors";

type Channel = "qr" | "non_qr";

export function EditAdvisorModal({
  advisor,
  onClose,
  onSaved,
}: {
  advisor: AdvisorDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [agencyCode, setAgencyCode] = useState(advisor.agency_code ?? "");
  const [agentCode, setAgentCode] = useState(advisor.agent_code ?? "");
  const [channel, setChannel] = useState<Channel>(advisor.channel);
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<"active" | "inactive">(advisor.status);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSave = async () => {
    setBusy(true);
    setError(null);
    try {
      // Send only the fields the staff member actually changed.
      const payload: Parameters<typeof updateAdvisor>[1] = {};
      if (agencyCode.trim() !== (advisor.agency_code ?? "")) payload.agency_code = agencyCode.trim();
      if (agentCode.trim() !== (advisor.agent_code ?? "")) payload.agent_code = agentCode.trim();
      if (channel !== advisor.channel) payload.channel = channel;
      if (status !== advisor.status) payload.status = status;
      if (password) payload.password = password;

      await updateAdvisor(advisor.id, payload);
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Edit Advisor"
      description={`${advisor.advisor_code} — Type controls the advisor's QR / Non QR channel`}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>
            Close
          </Button>
          <Button size="sm" onClick={onSave} loading={busy}>
            Save
          </Button>
        </>
      }
    >
      {error && <ErrorBanner message={error} />}
      <FormField
        id="advisor-name"
        name="full_name"
        label="Name"
        value={advisor.full_name}
        disabled
        readOnly
      />
      <FormField
        id="advisor-agency-code"
        name="agency_code"
        label="Agency Code"
        value={agencyCode}
        onChange={(e) => setAgencyCode(e.target.value)}
        placeholder="Agency code"
      />
      <FormField
        id="advisor-agent-code"
        name="agent_code"
        label="Agent Code"
        value={agentCode}
        onChange={(e) => setAgentCode(e.target.value)}
        placeholder="Agent code"
      />
      <FormField
        id="advisor-password"
        name="password"
        label="Password"
        type="password"
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Leave blank to keep the current password"
      />
      <SelectField
        id="advisor-channel"
        name="channel"
        label="Type"
        value={channel}
        onChange={(e) => setChannel(e.target.value as Channel)}
        options={[
          { value: "qr", label: "QR" },
          { value: "non_qr", label: "Non QR" },
        ]}
      />
      <SelectField
        id="advisor-status"
        name="status"
        label="Status"
        value={status}
        onChange={(e) => setStatus(e.target.value as "active" | "inactive")}
        options={[
          { value: "active", label: "Active" },
          { value: "inactive", label: "Inactive" },
        ]}
      />
    </Modal>
  );
}
