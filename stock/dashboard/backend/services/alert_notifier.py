"""Discord notifier for triggered alerts. Reads webhook URL from settings."""
import logging
import os
import sys

# sys.path bootstrap to import common.notify (repo-root-relative)
_here = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):
    if os.path.isdir(os.path.join(_here, "common")):
        sys.path.insert(0, _here)
        break
    _here = os.path.dirname(_here)

from common.notify import send_to_discord
from core.settings import settings

logger = logging.getLogger(__name__)


def notify_triggered(payload: dict, *, alert_id: int) -> None:
    """Send a Discord embed for a triggered alert.

    Silent no-op if webhook is unset (test/dev mode); failures are logged
    but never propagate (Discord delivery is best-effort).
    """
    webhook_secret = settings.discord_stock_webhook_url
    webhook = webhook_secret.get_secret_value() if webhook_secret else None
    if not webhook:
        logger.info("alert_notify_skipped alert_id=%s reason=no_webhook", alert_id)
        return
    try:
        send_to_discord(webhook, payload)
        logger.info("alert_notified alert_id=%s", alert_id)
    except Exception as e:
        logger.warning("alert_notify_failed alert_id=%s error=%s", alert_id, e)
