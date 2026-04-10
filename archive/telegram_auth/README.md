## Archived Telegram Auth

This directory stores the removed CRM login flow that used a one-time code
confirmed through a Telegram bot.

Archived on 2026-04-10 when the active CRM login was simplified to a regular
login/password flow.

Contents:
- `auth_service.py` - original code-based Telegram auth service
- `flask_routes.py` - removed Flask routes for Telegram login
- `templates/login.html` - removed Telegram login page
