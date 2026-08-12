# Notifications

## Channels

Email, SMS, WhatsApp, Push (future), In-App, Broadcast — owned by the `notification_management` feature module (scaffolded, empty). Delivery for SMS/WhatsApp/Email goes through the corresponding `app/services/{sms,whatsapp,email}` client stub, wired to real providers once System Settings/Integrations supplies credentials.

## Templates

Notification templates are DB-driven (never hardcoded), per the project's core rule — a template has a key, channel, and variable placeholders. The exact schema is defined when `notification_management` is planned.

## Notification Queue

Redis-backed (per the project's Redis-usage rule), consumed by Arq workers (`backend/app/worker/`) — see decision 002 for why Arq was chosen. No queue jobs exist yet; the Reminder Engine module adds the first ones.

## Reminder Engine Rules

From the project brief (see `docs/WORKFLOWS.md` for the full flow):

- **Re-Eligible Reminder**: a rejected lead becomes eligible again after 90 days; notify the employee 10 days before that date.
- **Task Reminder**: notify the assigned employee 1 hour before a task deadline; notify again if the deadline passes; notify the owner if it's still not completed after that.

Both are scheduled/recurring Arq jobs, not request-triggered — they need a job that runs periodically and checks for leads/tasks crossing these thresholds, added when the Reminders module is built.
