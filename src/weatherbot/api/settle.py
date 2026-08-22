"""Resolve open paper trades against `settlements` once the actual high
for their target_date is known, updating `trades` and `paper_wallet`.

Win condition per Kalshi's strike_type semantics (confirmed against live
market rules_primary text):
  - 'greater': YES wins if actual_high > bracket_high (bracket_high holds
    floor_strike's value for these markets; see note in resolve_side)
  - 'less':    YES wins if actual_high < bracket_high (cap_strike)
  - 'between': YES wins if bracket_low <= actual_high <= bracket_high
"""

import math
from decimal import Decimal

from sqlalchemy import text

from weatherbot.db import get_session

FEE_MULTIPLIER = Decimal("0.07")


def kalshi_fee(contracts: Decimal, price: Decimal) -> Decimal:
    """Taker fee: ceil(0.07 * contracts * price * (1-price) * 100) / 100."""
    raw = FEE_MULTIPLIER * contracts * price * (1 - price) * 100
    return Decimal(math.ceil(raw)) / 100


def yes_wins(strike_type: str, bracket_low, bracket_high, actual_high: Decimal) -> bool:
    if strike_type == "greater":
        return actual_high > bracket_low
    if strike_type == "less":
        return actual_high < bracket_high
    if strike_type == "between":
        return bracket_low <= actual_high <= bracket_high
    raise ValueError(f"Unknown strike_type: {strike_type}")


def resolve_pending_trades() -> int:
    """Settle every open paper trade whose target_date now has a settlement.
    Returns the number of trades resolved."""
    session = get_session()
    resolved = 0
    try:
        rows = session.execute(
            text(
                """
                SELECT t.id, t.side, t.price, t.size, t.strike_type,
                       t.bracket_low, t.bracket_high, t.fee, s.actual_high
                FROM trades t
                JOIN settlements s
                  ON s.date = t.target_date AND s.station = t.station
                WHERE t.status = 'open' AND t.is_paper_trade = TRUE
                """
            )
        ).fetchall()

        for row in rows:
            (trade_id, side, price, size, strike_type,
             bracket_low, bracket_high, fee, actual_high) = row

            contracts = Decimal(size) / Decimal(price)
            won = yes_wins(strike_type, bracket_low, bracket_high, actual_high)
            if side == "no":
                won = not won

            payout = contracts * Decimal("1.00") if won else Decimal("0.00")
            fee_dec = Decimal(fee or 0)
            pnl = payout - Decimal(size) - fee_dec
            status = "settled_win" if won else "settled_loss"

            session.execute(
                text("UPDATE trades SET status = :status, pnl = :pnl WHERE id = :id"),
                {"status": status, "pnl": pnl, "id": trade_id},
            )
            # Stake was already deducted from balance when the bet was placed
            # (execute_bet) but the fee was not - it's charged here, alongside
            # the payout, so balance ends up matching each trade's stored pnl.
            session.execute(
                text(
                    "UPDATE paper_wallet SET balance = balance + :payout - :fee, updated_at = now()"
                ),
                {"payout": payout, "fee": fee_dec},
            )
            resolved += 1

        session.commit()
    finally:
        session.close()
    return resolved


if __name__ == "__main__":
    count = resolve_pending_trades()
    print(f"Resolved {count} paper trade(s).")
