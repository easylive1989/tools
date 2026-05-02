"""CLI: issue / list / revoke API tokens.

Usage (from backend/):
  python -m scripts.issue_token issue --label paul-laptop
  python -m scripts.issue_token issue --label friend --expires-days 90
  python -m scripts.issue_token issue --label permanent --no-expiry
  python -m scripts.issue_token list
  python -m scripts.issue_token revoke <id>
"""
import argparse
import sys
from datetime import datetime, timezone

from core.logging import setup_logging
from db import init_db
from repositories.api_tokens import list_tokens, revoke_token
from services.token_service import issue_token


def cmd_issue(args: argparse.Namespace) -> int:
    expiry = None if args.no_expiry else args.expires_days
    plaintext, token_id = issue_token(label=args.label, expiry_days=expiry)
    print(f"Token id:    {token_id}")
    print(f"Label:       {args.label}")
    print(f"Expires:     {'never' if expiry is None else f'in {expiry} days'}")
    print(f"Token (only shown once):")
    print(f"  {plaintext}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    rows = list_tokens()
    if not rows:
        print("(no tokens)")
        return 0
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    print(f"{'ID':>4}  {'PREFIX':<14}  {'LABEL':<30}  {'CREATED':<24}  {'LAST_USED':<24}  {'STATUS':<10}")
    for r in rows:
        if r["revoked_at"]:
            status = "revoked"
        elif r["expires_at"] and r["expires_at"] < now_iso:
            status = "expired"
        else:
            status = "active"
        print(f"{r['id']:>4}  {r['prefix']:<14}  {r['label']:<30}  "
              f"{r['created_at']:<24}  {(r['last_used_at'] or '-'):<24}  {status:<10}")
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    ok = revoke_token(args.id)
    if ok:
        print(f"Revoked token id={args.id}")
        return 0
    print(f"Token id={args.id} not found or already revoked", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    init_db()

    parser = argparse.ArgumentParser(description="Stock Dashboard API token CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_issue = sub.add_parser("issue", help="issue a new token")
    p_issue.add_argument("--label", required=True, help="human-readable label")
    p_issue.add_argument("--expires-days", type=int, default=365, help="default 365")
    p_issue.add_argument("--no-expiry", action="store_true", help="never expires")
    p_issue.set_defaults(func=cmd_issue)

    p_list = sub.add_parser("list", help="list all tokens")
    p_list.set_defaults(func=cmd_list)

    p_revoke = sub.add_parser("revoke", help="revoke a token by id")
    p_revoke.add_argument("id", type=int)
    p_revoke.set_defaults(func=cmd_revoke)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
