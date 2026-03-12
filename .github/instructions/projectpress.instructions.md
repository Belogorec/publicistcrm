---
description: "Use when working on projectpress: Telegram bot for selling publication placement services. Covers architecture, funnel logic, media handling, CRM sync, payments, DB rules, admin approval flows, build/run commands."
applyTo: "projectpress/**"
---

# Projectpress Guidelines

## Project Purpose
- Telegram bot that sells publication placement services to clients.
- Manages a simple sales funnel: lead → materials collection → editor handoff → approval → payment → done.
- Integrates with cloud storage, a CRM system, and a bank mini app for acquiring.

## Architecture
- Stack mirrors luchbarbot: Flask webhook service + Telegram bot via webhook.
- Main entrypoint: `projectpress/flask_app.py`.
- Importing the app runs `bootstrap_schema()`, so schema migrations happen at startup.
- Keep module boundaries intact:
  - `tg_handlers.py` — Telegram webhook parsing, callback routing, admin checks, bot replies to clients.
  - `dialog.py` — funnel state machine: step definitions, transitions, user session management.
  - `materials_service.py` — receiving, validating, storing text and media materials from clients.
  - `cloud_service.py` — uploading materials to cloud storage; returns stable URLs for editor and DB.
  - `crm_service.py` — syncing deal and client data to the external CRM.
  - `payment_service.py` — mini app integration and bank acquiring webhook handling.
  - `admin_flow.py` — forwarding materials to editors, receiving approvals, relaying decisions back to clients.
  - `render.py` — building Telegram-facing HTML messages and inline keyboards.
  - `db.py` — SQLite connections, pragmas, schema creation, migrations (WAL mode, foreign keys, row factory).
  - `config.py` — all configuration via environment variables.

## Working Style
- Make minimal, surgical changes only.
- Do not refactor unrelated code.
- Preserve existing behavior unless the task explicitly requires changing it.
- Prefer backward-compatible changes.
- Follow patterns already used in the touched file before introducing new abstractions.
- Do not rename files, routes, callbacks, environment variables, DB columns, or public interfaces unless explicitly required.

## Build And Run
- Use Python 3.11.x.
- Install dependencies from `projectpress/requirements.txt`.
- Initialize schema with `cd projectpress && python init_db.py`.
- Run locally with `cd projectpress && python flask_app.py`.
- For production-like local runs:
  `cd projectpress && gunicorn flask_app:app --bind 0.0.0.0:5000 --workers 2 --timeout 120`
- No automated test suite — validate with targeted script runs, endpoint checks, or focused manual flows.

## Configuration
- All config via environment variables in `config.py`.
- Use `os.getenv(...).strip()` style consistently.
- Do not silently rename existing environment variable names.
- Required env vars (at minimum): `TELEGRAM_TOKEN`, `WEBHOOK_SECRET`, `CLOUD_BUCKET`, `CRM_API_URL`, `CRM_API_KEY`, `PAYMENT_PROVIDER_TOKEN`, `ADMIN_IDS`, `EDITOR_IDS`.

## Database Rules
- Use parameterized SQL only. No string interpolation in queries.
- Use `connect()` or `db()` from `db.py` for all DB access (WAL mode, foreign keys, row factory must stay consistent).
- Treat migrations as idempotent — safe to run on partially migrated environments.
- Core tables: `clients`, `deals`, `materials`, `approval_events`, `payments`.
- Do not change column semantics or table names without an explicit requirement.
- Be careful with anything touching deal status, material approval state, or payment records.

## Funnel And Dialog Logic
- Funnel steps are defined in `dialog.py` as an explicit state machine (step name → handler).
- Client session state (current step, collected data) is stored in the `clients` or `sessions` table, not in memory.
- Each step handler receives the Telegram update and returns the next step name or `None` (stay).
- Do not add implicit step transitions — all transitions must be explicit in the state machine.
- Preserve existing step names and transition logic unless explicitly required to change.

## Materials Handling
- Accept text messages and media (photos, documents) from clients at the appropriate funnel step.
- Validate file types and sizes before accepting; reject with a clear client-facing message if invalid.
- Store all received materials in the `materials` table with `deal_id`, `type`, `telegram_file_id`, and `cloud_url` after upload.
- Always upload to cloud before writing `cloud_url` to DB — never store local paths as permanent references.
- Never expose raw `telegram_file_id` to editors or CRM; use cloud URLs.

## Cloud Storage
- All uploads go through `cloud_service.py` — do not call cloud SDKs directly from handlers.
- Files are organized by deal: `<bucket>/<deal_id>/<filename>`.
- Upload is synchronous in the request cycle for now — do not add async queues without an explicit requirement.
- On upload failure, return an error to the handler; do not silently swallow failures.

## CRM Sync
- Sync happens after key deal events: lead created, materials submitted, approval given, payment confirmed.
- `crm_service.py` wraps all CRM API calls and handles retries and error logging.
- CRM sync failures must not break the main bot flow — log the error and continue.
- Do not duplicate client/deal data structures between the local DB and CRM mapping layer.

## Admin And Editor Approval Flow
- When a deal is ready for review, `admin_flow.py` forwards materials to the configured editor chat(s).
- Editors respond via inline keyboard (approve / request changes / reject).
- Approval events are recorded in `approval_events` with `deal_id`, `editor_id`, `decision`, `comment`, `ts`.
- On approval/rejection, the client receives an automated message with the decision and any comment.
- Do not change `callback_data` formats for approval keyboards unless explicitly required.
- Only users in `EDITOR_IDS` can submit approval decisions.

## Telegram Rules
- All Telegram messages use HTML formatting.
- Escape all user-controlled content (client names, material text, comments) before sending.
- Preserve existing callback routing patterns.
- Do not change inline keyboard ordering unless explicitly required.
- Do not change admin/editor moderation flows unless explicitly required.
- Be careful with reply, edit, and callback interactions — small format changes can break downstream handlers.

## Payments
- Payment is triggered via a Telegram Mini App link sent to the client at the payment step.
- Bank acquiring webhook hits `/webhook/payment` — validate the signature before processing.
- On confirmed payment, update deal status in DB and trigger CRM sync.
- Payment records store `deal_id`, `amount`, `currency`, `status`, `provider_payment_id`, `ts`.
- Do not change payment status values without updating all consumers.
- Never log full card or payment credential data.

## Webhook And API Safety
- Preserve existing webhook routes and request handling contracts unless explicitly required.
- Validate `WEBHOOK_SECRET` on all inbound Telegram webhooks.
- Validate payment provider signatures on all inbound payment webhooks.
- Do not remove defensive `try/except`, fallback branches, or compatibility code unless explicitly asked.

## Output Format For Changes
- Return the full function body or full code block being changed, not partial fragments.
- Always state the exact file being changed.
- Always state exactly what to replace.
- Prefer: `Replace function <name> in <file> with:` followed by the full updated function.
- If several connected edits are required, group them by file and function/block.

## What To Avoid
- Do not introduce new dependencies unless necessary.
- Do not perform broad refactors without an explicit request.
- Do not duplicate existing helpers for normalization, DB access, rendering, or admin checks.
- Do not change deal status logic, approval state machine, or payment confirmation flows without an explicit requirement.

## Validation Expectations
- After making a change, sanity-check with the smallest realistic validation:
  - import/load check,
  - endpoint check,
  - or a focused manual scenario through the affected flow.
- For payment and approval changes, trace the full event path before patching.
