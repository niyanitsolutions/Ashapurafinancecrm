# Voice security boundaries

Reuse existing bearer auth, session lifecycle, permission engine and safe error
envelopes. Company-wide knowledge requires explicit knowledge permissions. Calls
are scoped to creator for employees; Owner can see company records. This CRM has
no tenant context; multi-company hosting remains blocked until a cross-CRM tenant
migration and tests exist. Never accept a client-supplied tenant/caller assurance.

Campaigns reuse existing CRM customer/application scopes and retain customer
references rather than copied phone numbers. Employees cannot attest consent,
change suppression or change the emergency stop. Owner attestations are explicitly
unverified consent evidence, not independent authorization from the customer or
regulator. Consent withdrawal, global/campaign suppression and frequency limits
are checked against current records during dry-run processing. Dry runs cannot
change contact-frequency timestamps, invoke a carrier, charge services or enable
test/production mode. Cross-campaign live contact reservations and real provider
reconciliation must be implemented before dispatch can be considered safe.

Sensitive advisor credential/agency edits require their specific advisor or legacy
recruitment permission; general insurance business/application Edit is insufficient.
The linked Application remains the staff authorization source for insurance cases;
its employee assignment must never overwrite a workflow's advisor assignment.

Provider secrets use existing Fernet field encryption. Imported audio must use
encrypted private storage, authenticated playback, dedicated recording permissions,
minimal audit metadata and retention/deletion. Ordinary logs must not contain
audio, transcripts, knowledge content, tokens, customer numbers or playback URLs.
Imported transcript provenance is mandatory; operator-provided text is not verified
STT output. Consent references document evidence, not legal compliance or permission
to reuse recordings for model training. No secondary training use is enabled.

Uploads are untrusted. Enforce byte/expanded-content/row/cell/output bounds;
reject macros, formulas, external document relationships and unsupported content;
never execute instructions/scripts. Parser validation is not malware scanning.
Complex formats without an isolated/scanned parser remain blocked. Do not add
arbitrary URL ingestion without DNS/IP/redirect/allowlist policy. HTML from knowledge
is rendered as escaped text, never inserted as executable markup.

Retrieved documents and caller/model text cannot override immutable system policy.
Evaluation fact matching is a retrieval check, not proof of semantic correctness.
No unrestricted database queries, shell/URL tools or account lookups are offered
to a model. EMI/payment tools require verified identity and a real authoritative
payment source; loan-offer amounts are insufficient. Consequential actions need
confirmation and idempotency independently of model output.

Use unique keys/CAS for repeatable mutations and deny stale versions. Callback
auth is explicit; do not invent provider HMAC signatures. Public live audio remains
rejected until authenticated reserved sessions and origin/replay/backpressure
tests are complete. Error responses must not return parser contents or crypto paths.

Before live use, qualified personnel must verify Indian telecom/outbound rules,
recording/AI disclosure, consent/suppression, privacy/retention/export requests,
carrier contracts and self-hosted engine/model licenses. Software gates do not
establish legal compliance. No activation or compliance claim is made here.
