---
description: "Use when working on luchbarbot: Flask webhook service for bookings, Telegram bot, admin analytics. Covers architecture, DB rules, booking logic, Telegram rules, build/run commands."
applyTo: "luchbarbot/**"
---

# Luchbarbot Guidelines

## Architecture
- The app is a Flask webhook service for bookings, Telegram bot interactions, and admin analytics.
- Main entrypoint: `luchbarbot/flask_app.py`.
- Importing the app runs `bootstrap_schema()`, so schema migrations happen at startup.
- Production uses two Railway services with separate SQLite volumes:
  - `BOT_LUCH` keeps bot operational data in `/data/luchbar.db`.
  - `LUCH_crm` keeps CRM data in its own `/data/luchbar.db`.
  - These files are not shared automatically; writing to one service DB does not change the other.
- Bot and CRM are maintained in different GitHub repositories:
  - bot repo: `Belogorec/BOT_LUCH`
  - CRM repo: `Belogorec/LUCH_crm`
  - keep temporary migration artifacts (CSV/import scripts) out of `main` in both repos.
- Keep module boundaries intact:
  - `tg_handlers.py` handles Telegram webhook parsing, callback routing, admin checks, and bot replies.
  - `tilda_api.py` and `/api/booking` flows normalize external booking payloads.
  - `booking_service.py` owns booking and guest business logic.
  - `booking_render.py` builds Telegram-facing HTML messages and keyboards.
  - `db.py` owns SQLite connections, pragmas, schema creation, and migrations.

## Working Style
- Make minimal, surgical changes only.
- Do not refactor unrelated code.
- Do not rewrite large working sections when a small targeted patch is sufficient.
- Preserve existing behavior unless the task explicitly requires changing it.
- Prefer backward-compatible changes.
- Follow patterns already used in the touched file before introducing new abstractions.
- Do not rename files, routes, callbacks, environment variables, DB columns, helper functions, or public interfaces unless explicitly required.

## Build And Run
- Use Python 3.11.x.
- Install dependencies from `luchbarbot/requirements.txt`.
- Initialize schema with `cd luchbarbot && python init_db.py`.
- Run locally with `cd luchbarbot && python flask_app.py`.
- For production-like local runs, use:
  `cd luchbarbot && gunicorn flask_app:app --bind 0.0.0.0:5000 --workers 2 --timeout 120`
- There is currently no automated test suite in the workspace.
- Validate changes with targeted script runs, endpoint checks, or focused manual flows.

## Configuration
- Configuration is environment-driven in `config.py`.
- Keep new settings consistent with the existing `os.getenv(...).strip()` style where appropriate.
- Do not silently change existing environment variable names.
- `PROMO_ADMIN_IDS` may be provided as JSON, comma-separated, space-separated, newline-separated, or semicolon-separated input. Preserve that flexibility.

## Database Rules
- Use parameterized SQL only.
- Use `connect()` or `db()` from `db.py` instead of ad hoc SQLite setup so WAL mode, foreign keys, and row factories stay consistent.
- Treat migrations as idempotent.
- Schema bootstrapping must remain safe for partially migrated environments.
- Do not change DB schema semantics unless explicitly required.
- Be careful with anything affecting booking confirmation, visits, promo usage, or admin statistics.

## Booking And Guest Logic
- Reuse the existing normalization helpers for names, times, and especially phones.
- Russian phone normalization to E.164 is already implemented and must not be duplicated inconsistently.
- Preserve mixed Russian and English field-name handling in booking imports and Tilda payloads.
- Contact-sharing flow is authoritative for guest naming:
  - when Telegram contact is shared and phone matches an existing guest,
  - update `guests.name_last` with Telegram contact name.
- Be careful when changing booking confirmation logic: downstream visit creation depends on both `phone_e164` and `reservation_dt` being present.
- Guest segmentation and admin analytics use project-specific thresholds and timezone-offset behavior. Do not change them without an explicit requirement.

## CRM Sync And Backfill
- Bot-to-CRM live sync goes through `crm_sync.py` -> CRM endpoint `/api/events`.
- All booking creation paths must emit CRM upsert events:
  - `tg_handlers.py` miniapp message flow,
  - `tilda_api.py` webhook flow,
  - `flask_app.py` endpoint `/api/booking`.
- `backfill_crm.py` resends booking events only; it does not import historical `guest_visits` CSV datasets by itself.
- If a large legacy guest base must appear in CRM, import it directly into `LUCH_crm` DB (its own volume), not only into `BOT_LUCH`.
- Do not silently swallow sync failures:
  - keep retry logic in `crm_sync.py`,
  - write explicit `CRM_SYNC_FAIL` booking events for diagnostics.

## CRM UI Refresh
- CRM list/dashboard pages support auto-refresh via polling `GET /api/crm/pulse`.
- When troubleshooting "status refresh works but new booking does not", first verify that new booking events are delivered into CRM DB (not only updated inside BOT_LUCH).

## Migration Safety
- Before one-off data imports on Railway, create a DB backup in the same volume.
- Treat guest CSV files as sensitive contact data:
  - keep them git-ignored,
  - use temporary branches/commits only when strictly necessary,
  - remove temporary artifacts from `main` immediately after import.

## Telegram Rules
- Telegram messages use HTML formatting.
- Escape all user-controlled content before sending or editing messages.
- Preserve existing callback routing patterns.
- Do not change `callback_data` formats unless explicitly required.
- Do not change inline keyboard ordering unless explicitly required.
- Do not change admin moderation flows unless explicitly required.
- Be careful with reply, edit, and callback interactions: small format changes can break downstream handlers.

## Webhook And API Safety
- Preserve existing webhook routes and request handling contracts unless explicitly required.
- When editing booking flows, trace the full path before patching:
  inbound payload -> normalization -> DB write -> render -> Telegram send/edit/callback handling.
- Do not remove defensive `try/except`, fallback branches, or compatibility code unless the task explicitly requires cleanup.
- Prefer adding focused diagnostics rather than removing logging in webhook-critical paths.

## Output Format For Changes
- Return the full function body or full code block being changed, not partial fragments.
- Always state the exact file being changed.
- Always state exactly what to replace.
- Prefer instructions in this format:
  - `Replace function <name> in <file> with:`
  - followed by the full updated function.
- If several connected edits are required, group them by file and function/block.
- Do not provide abstract recommendations when the user asked for a concrete patch.

## What To Avoid
- Do not edit `luchbarbot — копия/` unless explicitly asked.
- Do not introduce new dependencies unless necessary.
- Do not perform broad refactors without an explicit request.
- Do not duplicate existing helpers for normalization, DB access, rendering, or admin checks.
- Do not change timezone logic, analytics thresholds, booking status logic, or confirmation side effects without an explicit requirement.

## Validation Expectations
- After making a change, sanity-check the affected flow with the smallest realistic validation:
  - import/load check,
  - endpoint check,
  - focused manual scenario,
  - or a small targeted script.
- For Telegram/admin/booking changes, prefer validating the exact affected branch instead of unrelated flows.
