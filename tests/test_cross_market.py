"""Unit tests for the cross-market scanner's pure logic: title matching
(precision-first), fee math, and executable-price arbitrage.

The cardinal sin in this module is a FALSE pair or a MIDPOINT-based edge
— either fabricates an arbitrage that doesn't exist. Tests pin both.
"""

from weatherbot.cross_market import (
    VenueQuote,
    best_arbitrage,
    kalshi_fee,
    match_pairs,
    score_match,
    tokenize,
)


def quote(source, bid, ask, title="t"):
    return VenueQuote(
        source=source,
        market_id="m",
        title=title,
        url=None,
        yes_bid=bid,
        yes_ask=ask,
        close_time=None,
        volume=None,
    )


# --- matching ------------------------------------------------------------


def test_tokenize_drops_stopwords_and_punctuation():
    toks = tokenize("Will the Fed cut rates in December?")
    assert "fed" in toks and "december" in toks
    assert "will" not in toks and "the" not in toks


def test_same_event_scores_above_threshold():
    a = "Will the Federal Reserve cut interest rates in December 2026?"
    b = "Fed rate cut in December 2026?"
    assert score_match(a, b) >= 0.55


def test_conflicting_numbers_never_match():
    # Different strike years / amounts must hard-fail even with high overlap.
    a = "Will Bitcoin close above $100,000 in 2026?"
    b = "Will Bitcoin close above $150,000 in 2027?"
    assert score_match(a, b) == 0.0


def test_unrelated_events_do_not_match():
    a = "Will the Chiefs win the Super Bowl?"
    b = "Will the Federal Reserve raise interest rates in March?"
    assert score_match(a, b) == 0.0


def test_too_few_shared_tokens_do_not_match():
    assert score_match("Mars landing 2030", "Mars bar sales") == 0.0


# --- fees ------------------------------------------------------------------


def test_kalshi_fee_formula():
    # Published taker fee: 0.07 * p * (1 - p) per contract, max at p=0.5.
    assert abs(kalshi_fee(0.5) - 0.0175) < 1e-9
    assert kalshi_fee(0.99) < kalshi_fee(0.5)


# --- arbitrage ---------------------------------------------------------------


def test_arb_uses_executable_asks_not_midpoints():
    # Mids are identical (0.50) — no midpoint edge. But YES is buyable on
    # Kalshi at 0.40 and NO is buyable on Polymarket at 1 - 0.65 = 0.35,
    # total 0.75 + fees < 1, so a real executable edge exists.
    k = quote("kalshi", 0.30, 0.40)
    p = quote("polymarket", 0.65, 0.70)
    arb = best_arbitrage(k, p)
    assert arb is not None
    assert arb["direction"] == "buy_yes_kalshi_buy_no_polymarket"
    expected = 1 - (0.40 + 0.35) - kalshi_fee(0.40)
    assert abs(arb["edge"] - round(expected, 4)) < 1e-9


def test_arb_negative_when_books_overlap_normally():
    # Normal tight market: hedged cost exceeds $1 once the spread is paid.
    k = quote("kalshi", 0.48, 0.52)
    p = quote("polymarket", 0.49, 0.51)
    arb = best_arbitrage(k, p)
    assert arb is not None
    assert arb["edge"] < 0


def test_arb_none_when_a_book_side_is_missing():
    k = quote("kalshi", None, None)
    p = quote("polymarket", 0.49, 0.51)
    assert best_arbitrage(k, p) is None


def test_arb_picks_the_better_direction():
    # YES cheap on Polymarket instead: 0.35 ask there, NO via Kalshi at
    # 1 - 0.60 = 0.40 -> cost 0.75.
    k = quote("kalshi", 0.60, 0.66)
    p = quote("polymarket", 0.30, 0.35)
    arb = best_arbitrage(k, p)
    assert arb["direction"] == "buy_yes_polymarket_buy_no_kalshi"
    expected = 1 - (0.35 + 0.40) - kalshi_fee(0.40)
    assert abs(arb["edge"] - round(expected, 4)) < 1e-9


# --- pair matching (outcome identity veto) -----------------------------------


def _named(source, question, outcome):
    q = VenueQuote(
        source=source,
        market_id=outcome,
        title=f"{question} — {outcome}",
        url=None,
        yes_bid=0.40,
        yes_ask=0.45,
        close_time=None,
        volume=None,
        outcome=outcome,
    )
    return q


def test_different_candidates_in_same_event_never_pair():
    # The shared question scores high on tokens alone — the outcome veto
    # is the only thing standing between this and a fabricated arbitrage.
    k = _named("kalshi", "Who will succeed Netanyahu as Prime Minister of Israel?", "Israel Katz")
    p = _named("polymarket", "Will Benjamin Netanyahu be the next Prime Minister of Israel?", "Benjamin Netanyahu")
    assert match_pairs([k], [p]) == []


def test_same_candidate_pairs():
    k = _named("kalshi", "Who will succeed Netanyahu as Prime Minister of Israel?", "Avigdor Lieberman")
    p = _named("polymarket", "Will Avigdor Lieberman be the next Prime Minister of Israel?", "Avigdor Lieberman")
    pairs = match_pairs([k], [p])
    assert len(pairs) == 1
    assert pairs[0]["kalshi"] is k and pairs[0]["polymarket"] is p


def test_sub_event_never_pairs_with_national_event():
    # Caught live 2026-11-08: this false pair showed the day's biggest
    # fake "edge" (+14c). The broad title's tokens are nearly all inside
    # the narrow title, but shared tokens cover only half of the larger
    # title -> specificity-symmetry veto.
    k = _named("kalshi", "Ohio House District 27 winner? (2028)", "Republican party")
    p = _named(
        "polymarket",
        "Will the Republican Party control the House after the 2028 elections?",
        "Republican",
    )
    assert match_pairs([k], [p]) == []
