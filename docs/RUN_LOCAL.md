# Running the CRM

Three ways to run the stack, depending on what you're doing. **`deployment/docker-compose.yml`, its Dockerfiles, and every API/business logic/auth/RBAC/schema file are identical across all three — nothing in this doc or in `scripts/dev/` ever modifies them.**

| | **Local Development** (day-to-day) | **Docker Development** (integration testing) | **Production Deployment** |
|---|---|---|---|
| MongoDB | **Local Windows Service** (standalone, no Docker) | Docker (replica set `rs0`) | Docker (replica set `rs0`) |
| Redis | **Local Windows Service** (standalone, no Docker) | Docker | Docker |
| Backend (FastAPI) | **local**, `uvicorn --reload` | Docker | Docker |
| Frontend (Vite) | **local**, `npm run dev` | Docker | Docker |
| Arq worker | **local, only when needed** | Docker | Docker |
| Config | `backend/.env.local` / `frontend/.env.local` | `backend/.env.development` (via `docker-compose.yml`) | `backend/.env.production` |
| Docker required? | **No — never started, never required** | Yes | Yes |
| Use when | Everyday feature work — fastest edit/reload loop, lowest resource use | Verifying the actual production-shaped stack (all 5 containers, replica set) before a release / staging push | Real deployment — AWS, CI/CD |

Local Development never starts, checks for, or depends on Docker in any way. Docker Development and Production Deployment both run the exact same `deployment/docker-compose.yml` unchanged — the only difference between them is which env file/secrets are supplied and where it's run (your machine for a pre-release check, vs. the real AWS environment for production/CI-CD).

---

## Local Development

**Prerequisites (one-time):**
- A local **MongoDB Windows Service** — install MongoDB Community Server for Windows (the installer sets it up as a Windows Service automatically, listening on `127.0.0.1:27017`, standalone — no replica set needed here, see "Why no replica set" below).
- A local **Redis Windows Service** — install a Windows-native Redis build (e.g. Memurai, or any Redis-for-Windows package that registers itself as a Windows Service) listening on `127.0.0.1:6379`.

Docker is not required for either of these, and `start-local` will never try to start Docker for you.

**1. Start everything:**

```bash
bash scripts/dev/start-local.sh
```
PowerShell: `.\scripts\dev\start-local.ps1`

This checks MongoDB, checks Redis, copies `backend/.env.local` into place, and starts the backend (`uvicorn --reload`) and frontend (`npm run dev`) as background processes with logs under `scripts/dev/.local-run/`. If either service isn't running, the script prints one of these and stops without starting anything:

```
MongoDB service is not running.
Please start MongoDB.
```
```
Redis service is not running.
Please start Redis.
```

> **First run can take up to a minute.** Spawning the backend/frontend involves a PowerShell process (used internally for reliable process/PID tracking on Windows — see script comments) whose cold start can be slow on some machines; this is normal, not a hang.

**2. Start the worker — only when you're testing Reminders (6D), Referral commission jobs (7), Lead Capture retry (9B), or Communication (9C):**

```bash
bash scripts/dev/start-worker.sh
```
PowerShell: `.\scripts\dev\start-worker.ps1`

Runs in the foreground — `Ctrl+C` to stop it. Requires MongoDB and Redis already running, same as above.

**3. Stop the backend/frontend:**

```bash
bash scripts/dev/stop-local.sh
```
PowerShell: `.\scripts\dev\stop-local.ps1`

Stops the backend and frontend processes cleanly (and their child processes — see "Why the scripts use PowerShell internally" below). Your MongoDB and Redis Windows Services are left running, since those are shared, long-lived local infrastructure, not per-session state.

### First-time setup (once)

```bash
cd backend && python -m venv .venv && source .venv/Scripts/activate && pip install -e ".[dev]" && cd ..
cd frontend && npm install && cd ..
```

(Skip this if `backend/.venv` and `frontend/node_modules` already exist.)

### Seed the database (once, or safe to re-run)

```bash
cd backend
source .venv/Scripts/activate
export BOOTSTRAP_OWNER_MOBILE=9000000001
export BOOTSTRAP_OWNER_PASSWORD='OwnerPass123'
python ../scripts/seed.py
cd ..
```

PowerShell:
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
$env:BOOTSTRAP_OWNER_MOBILE = "9000000001"
$env:BOOTSTRAP_OWNER_PASSWORD = "OwnerPass123"
python ..\scripts\seed.py
cd ..
```

This works against whichever MongoDB `backend/.env.local`/`.env.development`/`.env.production` currently points at — run it once against your local MongoDB Windows Service and that data stays there for every future Local Development session.

---

## Docker Development

Same `deployment/docker-compose.yml` used for Production Deployment, run locally — use this to verify the real production-shaped stack (all 5 containers, Mongo replica set) before a release, or to reproduce a bug that only shows up under that configuration.

**Start everything:**
```bash
bash scripts/dev/full-docker-up.sh    # PowerShell: .\scripts\dev\full-docker-up.ps1
```
(Unchanged — thin wrappers around `docker compose -f deployment/docker-compose.yml up -d --build`.)

**Seed the database** — same seed script, same command as above, since it's your host's Python talking to whichever MongoDB is exposed on `localhost:27017` at the time (Docker's, in this mode).

**Stop everything:**
```bash
bash scripts/dev/full-docker-down.sh    # or: .\scripts\dev\full-docker-down.ps1
```

---

## Production Deployment

Same `deployment/docker-compose.yml`, unchanged, deployed to AWS / CI-CD with production secrets (`backend/.env.production`). This doc doesn't cover the deployment pipeline itself — only that nothing about Local Development or Docker Development touches this path. If Docker Development works locally, the same compose file will behave identically in production, modulo the env file supplied.

---

## Switching between modes

- **Local Development → Docker Development:** `bash scripts/dev/stop-local.sh` first (stops your local backend/frontend), then `bash scripts/dev/full-docker-up.sh`. **Stop your local MongoDB and Redis Windows Services first** (`Stop-Service MongoDB`, and the equivalent for your Redis service) — Docker's `mongo`/`redis` containers listen on the same host ports (27017/6379) and will fail to bind them otherwise.
- **Docker Development → Local Development:** `bash scripts/dev/full-docker-down.sh` first (frees ports 27017/6379/8000/5173), start your local MongoDB and Redis Windows Services back up, then `bash scripts/dev/start-local.sh`.

The two modes use **different MongoDB data** (your Windows Service's own data directory vs. Docker's `mongo_data` volume) — they are not the same database, so don't expect data seeded in one to appear in the other.

---

## Why no replica set for local MongoDB

Production/Docker Mongo runs as a replica set (`docker/mongodb/Dockerfile` passes `--replSet rs0`) because `app/config/database.py:start_transaction` supports multi-document transactions, which require one. **No feature currently implemented in this codebase calls `start_transaction` — it has zero call sites today.** A standalone local MongoDB Windows Service is therefore safe for everything that exists right now. If a future module adds a transactional write path, Local Development would need to either enable a local replica set (`mongod --replSet rs0` + a one-time `rs.initiate()`) or that feature would need to be tested via Docker Development instead — noted here so it isn't a surprise later.

## Why the scripts use PowerShell internally (even the `.sh` ones)

Git Bash's own `command &` / `$!` does not reliably identify the *real* Windows process for a backgrounded `uvicorn`/`npm` child on this platform (verified: the captured PID belonged to a short-lived wrapper, not the actual server, so a later `taskkill` on it missed the real process entirely). `Start-Process -PassThru` reliably returns the true PID, so both `start-local.sh` and `start-local.ps1` delegate actual process spawning to PowerShell (`scripts/dev/_spawn-hidden.ps1`, an internal helper — not meant to be run by hand) and `stop-local` uses `taskkill /T /F` (tree-kill) on that real PID, which correctly also stops uvicorn's `--reload` child process and Vite's `node` child. This is PowerShell used as a process-spawning primitive on native Windows — it is not WSL, and no WSL layer is involved anywhere in Local Development.

## URLs (all modes — same ports either way)

| What | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API base | http://localhost:8000/api/v1 |
| Swagger / OpenAPI UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Health check | http://localhost:8000/api/v1/health |

## Verifying each piece

- **MongoDB (Local Development):** `mongosh --eval "db.adminCommand('ping')"` → `{ ok: 1 }`. No replica set status to check (standalone).
- **MongoDB (Docker Development / Production):** `docker compose -f deployment/docker-compose.yml exec mongo mongosh --quiet --eval "db.adminCommand('ping')"`.
- **Redis:** `redis-cli -h localhost -p 6379 ping` → `PONG`.
- **Backend:** `curl http://localhost:8000/api/v1/health` → `{"success":true,"data":{"mongo":true,"redis":true,"status":"ok"},...}`.
- **Authentication / Login:** log in via the frontend, or `POST /api/v1/auth/login` with your seeded Owner credentials — exercises both Mongo (user lookup) and Redis (rate limiting, required by the route) in one call.
- **Lead creation:** create a Lead from the frontend (Leads → New Lead) or `POST /api/v1/leads` — confirms Mongo writes and the Lead Sources master data are working.
- **Customer / Loan / Insurance:** open Customers, Loan Cases, and Insurance Cases list pages — confirms the Customer Onboarding, Loan, and Insurance modules read correctly against Local Development's Mongo.
- **Employee:** open the Employees list and an Employee's profile tabs — confirms the Employee + Access Control modules.
- **Dashboard:** the Dashboard page renders its widget rows — confirms the reporting/aggregation queries run against local Mongo.
- **Notifications:** the notification bell / in-app notifications list loads — confirms Module 6D's read path.
- **Worker:** its terminal prints Arq's startup banner and a line per cron job as it fires (e.g. `poll_business_events()` — Module 9C, every 2 minutes).
- **Frontend:** the login page loads without console errors.
- **Logs (Local Development):** `tail -f scripts/dev/.local-run/backend.log` / `.../frontend.log` (or `Get-Content -Wait` in PowerShell).

## Default Owner login

No Owner exists until you run the seed script with `BOOTSTRAP_OWNER_MOBILE`/`BOOTSTRAP_OWNER_PASSWORD` set (Owner/Employee have no self-signup by design). Using the example values above: mobile `9000000001`, password `OwnerPass123`.

## Common failure → fix

| Symptom | Likely cause | Fix |
|---|---|---|
| `start-local.sh`/`.ps1` prints "MongoDB service is not running." and exits | Your local MongoDB Windows Service isn't running (or isn't installed yet) | `net start MongoDB` (find the exact service name: `sc query state=all \| findstr /i mongo`, or `Get-Service *mongo*` in PowerShell). Install MongoDB Community Server if you don't have it |
| `start-local.sh`/`.ps1` prints "Redis service is not running." and exits | Your local Redis Windows Service isn't running (or isn't installed yet) | Start your Redis Windows Service (e.g. `net start Memurai`, or whatever your Redis-for-Windows package registered — find it with `Get-Service *redis*` / `Get-Service *memurai*`). Install one if you don't have it — Local Development requires a real Windows Service, not Docker |
| Backend log shows `pydantic_core.ValidationError: ... Field required` for `mongo_uri`/`redis_url`/etc. | You ran `uvicorn`/`arq` directly instead of through the start scripts, so `backend/.env` (copied from `.env.local`) was never created — `Settings` (`app/config/settings.py`) only auto-loads a file literally named `.env` | Always start via `start-local.sh`/`.ps1` or `start-worker.sh`/`.ps1` — they copy `.env.local` → `.env` for exactly this reason. (Don't rely on shell-exported env vars alone: verified live that uvicorn `--reload`'s worker subprocess, re-spawned via Python's `multiprocessing` on Windows, does not reliably inherit them.) |
| `start-local.sh` seems to hang for a while on `== Backend ==` | Normal on some machines — the internal PowerShell helper's cold start can take up to ~30-60s the first time, especially under antivirus scanning | Wait for it to finish; it isn't stuck. If it genuinely never returns (multiple minutes), check for leftover orphaned processes from a previous run (see next row) |
| Repeated start/stop cycles leave things in a weird state (port already in use, log file "busy") | An earlier `start-local` run's processes weren't fully cleaned up (e.g. the terminal was closed instead of running `stop-local.sh`) | `bash scripts/dev/stop-local.sh` first; if that reports "already stopped" but port 8000/5173 is still occupied, find and end the stray process: PowerShell `Get-Process python,node -ErrorAction SilentlyContinue \| Stop-Process -Force` |
| PowerShell error: *"running scripts is disabled on this system"* when running any `.ps1` here directly | Legacy Windows PowerShell (`powershell.exe`) defaults to a `Restricted` execution policy that blocks local `.ps1` files entirely | Prefer PowerShell 7 (`pwsh`) — its default `RemoteSigned` policy allows local scripts to run. If you must use legacy `powershell.exe`, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (or invoke this one script with `powershell -ExecutionPolicy Bypass -File scripts\dev\start-local.ps1`) |
| Login/OTP requests fail even though the backend is up | Redis isn't actually reachable despite the service check passing (e.g. it's bound to a different interface/port) | `redis-cli -h localhost -p 6379 ping`; fix your Redis Windows Service configuration so it listens on `127.0.0.1:6379` |
| Two things fighting over port 8000, 5173, 27017, or 6379 | Local Development and Docker Development running at the same time | Stop one — see "Switching between modes" above |
| Worker prints `--- Logging error --- UnicodeEncodeError: 'charmap' codec can't encode character '→'` | Cosmetic only — `arq`'s own log formatting uses a Unicode arrow character that the legacy Windows console codepage (cp1252) can't display; the worker keeps running normally despite the traceback | Ignore it, or set `$env:PYTHONUTF8 = "1"` (PowerShell) / `export PYTHONUTF8=1` (bash) before starting the worker to silence it |

## No code changes required

Local Development required zero changes to `backend/app/`, `frontend/src/`, any API, database schema, authentication logic, RBAC, tenant architecture, or workflow code. Everything above lives in `scripts/dev/`, two `.env.local` files, and this doc. `deployment/docker-compose.yml` is untouched and Docker Development / Production Deployment behave exactly as before.
