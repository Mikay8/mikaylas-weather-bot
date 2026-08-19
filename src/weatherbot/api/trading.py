"""Shared bet-placement logic used by both the manual /api/wallet/bet
endpoint and the auto-trading bot, so pricing/fee/balance rules can't drift
between a human-placed and bot-placed trade."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from weatherbot.api.settle import kalshi_fee


class BetError(Exception):
    """Raised for any condition that should reject a bet (bad price, insufficient
    balance, unknown market) - callers map this to whatever's appropriate for
    their context (HTTP 422, a skipped bot cycle, etc.)."""


def execute_bet(
    session: Session,
    contract_id: str,
    side: str,
    amount: float,
    is_bot_trade: bool = False,
) -> dict:
    if side not in ("yes", "no"):
        raise BetError("side must be 'yes' or 'no'")
    if amount <= 0:
        raise BetError("amount must be positive")

    market = session.execute(
        text(
            """
            SELECT contract_id, target_date, bracket_low, bracket_high, strike_type,
                   yes_bid, yes_ask
            FROM market_snapshots
            WHERE contract_id = :contract_id
            ORDER BY timestamp DESC
            LIMIT 1
            """
        ),
        {"contract_id": contract_id},
    ).fetchone()
    if market is None:
        raise BetError("Market not found")
    if market.target_date is None:
        raise BetError("Market has no resolvable target_date")

    # You pay the ask side: yes_ask to buy YES, (1 - yes_bid) i.e. no_ask to buy NO.
    if side == "yes":
        price = market.yes_ask
    else:
        price = Decimal("1") - market.yes_bid if market.yes_bid is not None else None
    if price is None or price <= 0 or price >= 1:
        raise BetError("No valid price available for this side")

    amount_dec = Decimal(str(amount))
    wallet = session.execute(text("SELECT balance FROM paper_wallet LIMIT 1")).fetchone()
    if wallet.balance < amount_dec:
        raise BetError("Insufficient paper balance")

    contracts = amount_dec / price
    fee = kalshi_fee(contracts, price)

    now = datetime.now(timezone.utc)
    session.execute(
        text(
            """
            INSERT INTO trades
                (contract_id, timestamp, side, price, size, is_paper_trade, status,
                 target_date, bracket_low, bracket_high, strike_type, fee, is_bot_trade)
            VALUES
                (:contract_id, :timestamp, :side, :price, :size, TRUE, 'open',
                 :target_date, :bracket_low, :bracket_high, :strike_type, :fee, :is_bot_trade)
            """
        ),
        {
            "contract_id": contract_id,
            "timestamp": now,
            "side": side,
            "price": price,
            "size": amount_dec,
            "target_date": market.target_date,
            "bracket_low": market.bracket_low,
            "bracket_high": market.bracket_high,
            "strike_type": market.strike_type,
            "fee": fee,
            "is_bot_trade": is_bot_trade,
        },
    )
    session.execute(
        text("UPDATE paper_wallet SET balance = balance - :amount, updated_at = now()"),
        {"amount": amount_dec},
    )
    session.commit()
    return {
        "contract_id": contract_id,
        "side": side,
        "price": float(price),
        "contracts": float(contracts),
        "fee": float(fee),
        "amount_spent": float(amount_dec),
    }
