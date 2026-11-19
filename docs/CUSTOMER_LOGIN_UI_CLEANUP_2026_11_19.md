# Customer Login UI cleanup — 19 November 2026

Implemented locally only; not deployed.

The customer PIN card now shows mobile, PIN, Show PIN, Log in, Forgot PIN, and Create New Account in that order. The existing migration/password sign-in action sits below the PIN card in the former account-link position. The First-time verification / Create PIN link is removed.

Changed files:

- `frontend/src/features/auth/components/PinAuthPanel.tsx`: rearrange presentation links only; preserve Forgot PIN, migration callback, existing policy gate and PIN verification logic.
- `frontend/src/features/auth/pages/LoginPage.tsx`: remove the former bottom Create New Account link. Its `/create-account` destination and encoded return path are preserved in the relocated link.
- Corresponding `PinAuthPanel.test.tsx` and `LoginPage.test.tsx`: exercise recovery through Forgot PIN, link order, registration return path, migration and the internal login tab.

Validation:

- Auth and registration frontend suites: **18 tests passed**, four files, 8.47 seconds.
- Targeted ESLint: **passed**, no warnings/errors.
- TypeScript: `npm --prefix frontend run typecheck` **passed**.
- Production build: `npm --prefix frontend run build` **passed**; existing bundle-size advisory remains.
- Browser: **390px mobile, 768px tablet, 1366px desktop passed** exact visual order, absent redundant link, one visible account-creation link, unchanged registration route/return path, Forgot PIN entry, migration/password form entry, unchanged employee/partner tab, no overflow and no runtime errors. Policy/registration-status responses were mocked; no OTP was requested or SMS sent. Screenshots were inspected.
- `git diff --check`: **passed**.

Backend APIs, registration implementation, PIN creation/verification, sessions, permissions, schemas, Airtel and internal login implementations were not changed. Migration remains visible under the same existing enrollment-policy condition; this change does not bypass that condition.

Evidence: [browser results](screenshots/customer-login-cleanup-2026-11-19/results.json), [mobile screenshot](screenshots/customer-login-cleanup-2026-11-19/login-390.png).
