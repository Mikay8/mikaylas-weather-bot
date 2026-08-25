"""Email alerts for bot-placed trades via Resend's API. No-ops quietly if
RESEND_API_KEY / NOTIFY_EMAIL_TO aren't set (e.g. local dev) so this is
never a hard dependency of the trading path — a failed or skipped email
must never block or roll back a trade that already executed.
"""

import logging
import os

import httpx

RESEND_API_URL = "https://api.resend.com/emails"
FROM_ADDRESS = "Weather Bot <onboarding@resend.dev>"

logger = logging.getLogger(__name__)


def send_trade_email(trade: dict, rec: dict) -> None:
    api_key = os.environ.get("RESEND_API_KEY")
    to_addr = os.environ.get("NOTIFY_EMAIL_TO")
    if not api_key or not to_addr:
        return

    contract_id = trade["contract_id"]
    side = trade["side"].upper()
    model_prob = rec.get("model_prob")
    fee_adjusted_edge = rec.get("fee_adjusted_edge")
    predicted_high = rec.get("predicted_high")
    label = rec.get("kalshi_label") or contract_id
    confidence_pct = f"{model_prob * 100:.1f}%" if model_prob is not None else "n/a"
    edge_pct = f"{fee_adjusted_edge * 100:.1f}%" if fee_adjusted_edge is not None else "n/a"

    subject = f"Bot placed a {side} trade — {label} ({confidence_pct} confidence)"
    text_body = (
        f"The bot placed a paper trade.\n\n"
        f"Market: {label} ({contract_id})\n"
        f"Side: {side}\n"
        f"Price: {trade['price']:.2f}\n"
        f"Amount: ${trade['amount_spent']:.2f} ({trade['contracts']:.1f} contracts)\n"
        f"Fee: ${trade['fee']:.2f}\n\n"
        f"Model confidence: {confidence_pct}\n"
        f"Fee-adjusted edge: {edge_pct}\n"
        f"Predicted high: {predicted_high}\n"
    )

    try:
        response = httpx.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": FROM_ADDRESS,
                "to": [to_addr],
                "subject": subject,
                "text": text_body,
            },
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Failed to send trade notification email")
