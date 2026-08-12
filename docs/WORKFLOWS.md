# Workflows

Transcribed from the project brief. These describe intended behavior — implementation follows once the owning module is planned; this document is the reference, not a promise of current implementation state.

## Owner

Login → Dashboard → View New Leads → Assign Employee → Employee Processes → Monitor Progress → Reports → Revenue

## Employee

Login → Assigned Leads → Call Customer → Generate Secure Link → Customer Completes Application → Verify Documents → Bank Processing → Update Status → Complete

## Customer

Receive Secure Link → Register/Login → Open Assigned Form → Fill Application → Upload Documents → Submit → Track Status → Wait for Updates

Customer cannot edit after submission unless enabled by the employee or owner. See decision 003 for the secure-link + account auth model that backs "Receive Secure Link → Register/Login."

## Referral Partner

Login → Add Lead → Owner Receives → Assign Employee → Process → Disbursement → Commission Generated → Payment

Commission calculation rules are not yet defined — see `docs/roadmap/TODO.md`.

## Lead Intake

Website → CRM → Duplicate Check → Owner → Assign Employee → Customer Contact → Generate Link → Customer Form → Documents → Verification → Bank → Disbursement → Completed

## Lead Status (Loan product default — see decision 004 for why this isn't universal)

Historical brief transcription (superseded by the actual Module 6C implementation below): New Customer (AFS ID) → Application Incomplete → Documents Pending → Bank/NBFC Name + Application ID → Credit Evaluation → Offer Acceptance Pending → Upload Additional Documents → e-Sign Agreement → NACH Pending → KYC Pending → Final Evaluation → Application Rejected (Reason Required) / Send for Disbursement → Disbursed.

## Loan Processing Pipeline (Module 6C, implemented and frozen)

`docs/MODULE_6C_WORKFLOW_PROPOSAL.md` (approved) took precedence over the example sequence above wherever the two differed — see `docs/decisions/DECISIONS.md` #054–#061, #064 for the full rationale. Implemented sequence:

New Customer → Documents Pending → Credit Evaluation → **Rejected** (Reason Required) *or* Offer Acceptance → Upload Additional Documents → eSign / NACH / KYC → Final Evaluation → **Rejected** (Reason Required) *or* Send for Disbursement → Disbursed

Rejection is reachable from **two** points — Credit Evaluation and Final Evaluation (decision 055, resolving the "open question" this doc previously flagged) — not only the final step. Bank/NBFC Name, Application ID, Reference Number, Assigned Officer, Decision, and Remarks are recorded as fields on the case (`POST /loan-cases/{id}/bank-details`), editable at any point before disbursement, rather than their own pipeline stage (decision 061). No rollback exists in this version (decision 056) — but any non-terminal status can be placed **On Hold** and later **Resumed** back to exactly where it paused (decision 064; reasons: waiting for customer/bank/insurance company, internal review, document clarification) — a temporary pause, not a rollback to an earlier stage.

## Insurance Processing Pipeline (Module 6C, implemented and frozen — its own lifecycle, not a copy of Loan)

Finalized by the user (decision 064), superseding the earlier draft flagged as an assumption (decision 057):

Application Submitted → Documents Pending → Underwriting → **Rejected** (Reason Required) *or* [Medical Verification (optional) → **Rejected** (Reason Required) *or*] [Additional Documents (optional) →] Premium Acceptance → **Rejected** (on decline) *or* Policy Generation → Policy Issued

- **Medical Verification** and **Additional Documents** are both optional, per-case flags (`requires_medical`, `requires_additional_documents`) recorded once during Underwriting — never a fixed product attribute. A case needing both passes through Medical Verification, then Additional Documents, in that order.
- **Policy Generation** (the policy number/document is prepared) and **Policy Issued** (terminal) are two distinct business events, not one — generating the policy number does not itself issue it.
- Same On Hold / Resume capability as Loan (decision 064) — reachable from every non-terminal status.

## Reminder & Notification Engine (Module 6D, implemented and frozen)

Internal database notifications only — no WhatsApp/SMS/Email/push/external API this round; see `docs/decisions/DECISIONS.md` #065–#072.

**Re-Eligible Reminder:** Rejected (Loan/Insurance Case, Module 6C) → Eligible After 90 Days → Notify 10 Days Before → Employee Notification. Both numbers are `reminder_rules` values, Owner-editable, never hardcoded.

**Task Reminder:** Owner Assigns Task → Notify Employee (immediately, on assignment) → 30 Minutes Before Due → Notify Employee → Deadline Passed → Notify Employee Again (repeating every `escalation_repeat_minutes`) → Still Not Completed After `escalation_max_repeats` → Notify Owner (once; the task is then marked `owner_escalated` so this final step never repeats).

**Internal Notification Queue:** New Lead Assigned → Employee Notification; Documents Uploaded → Employee Notification (both by polling the existing `audit_logs` collection, decision 065 — no live hook into Leads/Customer's frozen code); Task Due / Reminder Triggered → Notification (generated directly by this module's own jobs). Every notification tracks unread/read/archived/dismissed + created/read timestamps (Notification History), self-service per user.

**Scheduler:** the first real Arq jobs (`app/worker/tasks/reminders.py`) — `poll_audit_events` (every 5 min), `check_task_reminders` (every 15 min), `check_re_eligible_cases` (daily).
