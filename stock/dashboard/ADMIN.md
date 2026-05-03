# Stock Dashboard — Admin Runbook

Operational notes for managing users + API tokens. The dashboard runs on a
VPS as a `systemd` service (`stock-dashboard.service`); the SQLite DB
lives at `/opt/stock-dashboard/backend/stock_dashboard.db`.

## Authentication model

- Each `user` (id, name, created_at) has **at most one active API token**.
- Issuing a new token for a user **revokes the previous active token
  immediately**. Any client still holding the old token will get 401.
- Tokens are 39-char `sd_<base64>` strings; only the SHA-256 hash + the
  display prefix (first 6 chars) are stored. **Plaintext is shown once at
  issue time.**
- Token expiry defaults to 365 days; pass `--no-expiry` to issue a
  permanent token. Expired tokens fail auth and need rotation.
- The `watched_stocks` (watchlist) and `price_alerts` (price alerts) tables
  scope by `user_id`. `/api/dashboard`, news, and per-ticker detail
  endpoints are open to any valid token.

## Where the CLI lives

The CLIs run on the VPS where the DB and venv exist:

```bash
ssh root@<VPS_HOST>
cd /opt/stock-dashboard/backend
source .venv/bin/activate                   # uvicorn's venv
```

All commands below assume that working directory + activated venv.

## User management — `manage_users.py`

```bash
# List all users (always shows 'paul' as id=1, the migrated default)
python -m scripts.manage_users list

# Create a new user. Errors with exit 1 if the name already exists.
python -m scripts.manage_users create alice
```

The new user starts with no token and an empty watchlist + alerts.

## Token management — `issue_token.py`

### Issue / rotate a user's token

```bash
# 365-day default expiry
python -m scripts.issue_token issue --user-name alice --label alice-laptop

# Custom expiry
python -m scripts.issue_token issue --user-name alice --label tmp --expires-days 30

# Permanent (no expiry — use sparingly)
python -m scripts.issue_token issue --user-name alice --label permanent --no-expiry
```

If a prior active token exists for that user, it's automatically revoked
in the same transaction. The plaintext token prints to stdout — copy it
once; you cannot recover it later.

If the user doesn't exist the script errors with a pointer:

```
error: user 'bob' not found.
  Run: python -m scripts.manage_users create bob
```

### List tokens

```bash
python -m scripts.issue_token list
```

Output columns: `ID | USER | PREFIX | LABEL | CREATED | LAST_USED | STATUS`.
`STATUS` is one of `active / expired / revoked`. `LAST_USED` updates on
every authenticated request.

### Manual revoke

Used only when you can't reach the user to rotate (compromise, lost
device). Identify the row id from `issue_token list`, then:

```bash
python -m scripts.issue_token revoke 7
```

## Common workflows

### Onboard a new user

```bash
python -m scripts.manage_users create $NAME
python -m scripts.issue_token issue --user-name $NAME --label $NAME-laptop
# share plaintext token via private channel
```

The user pastes the token into the dashboard's TokenGate
(`https://paul-learning.dev/tools/stock/`); it's stored in `localStorage`
and re-sent as `Authorization: Bearer <token>` on every API request.

### Rotate (expiry approaching, or device replaced)

```bash
python -m scripts.issue_token issue --user-name $NAME --label $NAME-newlaptop
```

The previous active token is revoked the moment this command commits. The
user should clear localStorage on their old device (or log out via the
dashboard's settings) and paste the new token on the new device.

### Audit access

```bash
python -m scripts.manage_users list
python -m scripts.issue_token list
```

Compare `LAST_USED` to a recent timestamp — long gaps suggest a stale
token that can be revoked.

### Emergency: revoke everything for a user

There's no `revoke-all-for-user` shortcut; rotate-and-discard works:

```bash
python -m scripts.issue_token issue --user-name $NAME --label emergency-rotate \
    --expires-days 1
# Don't share the new token; let it expire in 24h.
```

Or revoke directly by id from the `list` output.

## Database notes

The schema is managed by the migration runner (`db/runner.py`). Migrations
live in `backend/db/migrations/`; they apply on `init_db()` startup, which
runs whenever the `systemd` service restarts.

The user concept landed in migration `0003_users.sql`:

- New `users` table seeded with `paul` (id=1)
- `api_tokens` gets `user_id` FK + partial UNIQUE index
  `(user_id) WHERE revoked_at IS NULL` to enforce 1 active token per user
- `price_alerts` gets `user_id` FK
- `watched_stocks` is rebuilt to use `UNIQUE(user_id, ticker)` so two
  users can independently watch the same ticker
- All existing rows are backfilled to `user_id=1`

Direct DB inspection is fine for auditing:

```bash
sqlite3 /opt/stock-dashboard/backend/stock_dashboard.db
sqlite> SELECT u.name, COUNT(w.id) AS tickers, COUNT(a.id) AS alerts
   ...> FROM users u
   ...> LEFT JOIN watched_stocks w ON w.user_id = u.id
   ...> LEFT JOIN price_alerts a ON a.user_id = u.id
   ...> GROUP BY u.id;
```

## Frontend coordination

The frontend is unaware of the user concept — it just sends the token in
the Authorization header. Backend resolves `token → user_id` per request.
On 401 (expired/revoked), `apiFetch` clears `localStorage` and the
`TokenGate` reappears, prompting the user to paste a fresh token.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `401 Token user not found` after rotation | DB inconsistency (orphaned api_tokens row) | Inspect `SELECT * FROM api_tokens WHERE user_id NOT IN (SELECT id FROM users)`; if any, revoke or delete |
| `IntegrityError: UNIQUE constraint failed: api_tokens.user_id` on issue | Active row exists but `revoke_token` didn't update | Re-run `issue_token issue` (the script revokes-then-inserts in one transaction); if persistent, manually `UPDATE api_tokens SET revoked_at = datetime('now') WHERE user_id = ? AND revoked_at IS NULL` |
| User reports working token suddenly returns 401 | Someone else rotated (`issue_token issue` for the same user) | List tokens to see which row is now active; reissue if intended, or revoke the unintended one |
| Discord ops alert: `Stock Dashboard auth burst` | 5+ 401s from one IP in 5 min | Check logs (`journalctl -u stock-dashboard.service`) for the IP / token prefix; could be a stale token on a polling client, or scanning attempt |

## Service control

```bash
systemctl status  stock-dashboard.service
systemctl restart stock-dashboard.service       # also re-runs migrations
journalctl -u     stock-dashboard.service -f    # tail logs
```

CI deploy via `.github/workflows/deploy-stock-dashboard-backend.yml` runs
the rsync + restart on every push that touches `stock/dashboard/backend/**`.
