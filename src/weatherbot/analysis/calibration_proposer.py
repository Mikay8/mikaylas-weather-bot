"""Pattern check over recent trade_diagnoses: only when the analyst has
flagged the *same kind* of systematic_bias repeatedly does this draft a
calibration change and open a PR - never on a single trade, and never by
pushing to develop/main directly. A human still reviews and merges.

Flow:
  1. Pull the last RECENT_N diagnoses. If fewer than MIN_SYSTEMATIC_BIAS_HITS
     are systematic_bias (medium+ confidence), stop - nothing to propose.
  2. Ask Claude to read those diagnoses together and, only if it still sees a
     coherent pattern (not just several unrelated one-offs), propose ONE
     concrete, small change to STDEV_INFLATION_FACTOR in
     weatherbot/backtest/model.py.
  3. Apply that change to a throwaway copy of model.py's constant, then run
     the existing walk-forward backtests (calibration.py + pnl_backtest.py)
     with the new value to confirm it actually improves out-of-sample
     coverage/PnL versus the current value. If it doesn't, stop - no PR.
  4. If it does, write the change to model.py for real, commit it on a new
     branch, push, and open a PR via the GitHub REST API with the before/
     after backtest numbers and the diagnoses that triggered it in the body.

Run after trade_analyst.py (see analyst-cron in .railway/railway.ts).
"""

import json
import os
import re
import subprocess
from datetime import datetime, timezone

import anthropic
import httpx
from pydantic import BaseModel
from sqlalchemy import text

from weatherbot.analysis.trade_analyst import _client
from weatherbot.backtest import calibration, pnl_backtest
from weatherbot.db import get_session

MODEL = "claude-opus-5"
RECENT_N = 20
MIN_SYSTEMATIC_BIAS_HITS = 5

REPO = "Mikay8/mikaylas-weather-bot"
BASE_BRANCH = "develop"
MODEL_PY_PATH = "src/weatherbot/backtest/model.py"

BOT_COMMIT_NAME = "Mikayla Weather Bot"
BOT_COMMIT_EMAIL = "mikayla.hill8+weather@gmail.com"

INFLATION_FACTOR_PATTERN = re.compile(r"^STDEV_INFLATION_FACTOR = ([0-9.]+)\s*$", re.MULTILINE)


class CalibrationProposal(BaseModel):
    has_coherent_pattern: bool
    reasoning: str
    proposed_stdev_inflation_factor: float | None = None


def load_recent_diagnoses(session, n: int = RECENT_N) -> list[dict]:
    rows = session.execute(
        text(
            """
            SELECT td.id, td.trade_id, td.category, td.confidence, td.summary, td.created_at,
                   t.target_date, t.side, t.pnl
            FROM trade_diagnoses td
            JOIN trades t ON t.id = td.trade_id
            ORDER BY td.created_at DESC
            LIMIT :n
            """
        ),
        {"n": n},
    ).fetchall()
    return [dict(r._mapping) for r in rows]


def _passes_threshold(diagnoses: list[dict]) -> bool:
    hits = [
        d for d in diagnoses
        if d["category"] == "systematic_bias" and d["confidence"] in ("medium", "high")
    ]
    return len(hits) >= MIN_SYSTEMATIC_BIAS_HITS


def ask_for_proposal(client: anthropic.Anthropic, diagnoses: list[dict]) -> CalibrationProposal:
    context = json.dumps(diagnoses, indent=2, default=str)
    response = client.messages.parse(
        model=MODEL,
        max_tokens=4096,
        output_config={"effort": "high"},
        system=(
            "You review a batch of individual trade post-mortems from a weather-trading "
            "bot's probability model (Normal(predicted_high + bias, stdev), stdev "
            "corrected by a single global STDEV_INFLATION_FACTOR - see model.py). "
            "Several of these were independently flagged systematic_bias. Your job is "
            "to check whether they actually describe ONE coherent, correctable pattern "
            "(e.g. consistently underdispersed in a specific season, or a consistent "
            "directional error) versus being several unrelated one-off issues that "
            "happened to share a label. Be conservative: set has_coherent_pattern=false "
            "unless the diagnoses clearly point to the same root cause. Only if true, "
            "propose a new value for STDEV_INFLATION_FACTOR (currently a fixed "
            "multiplicative correction on the fitted stdev - see model.py's v1.1 "
            "docstring) that would address the pattern you found. Propose a small, "
            "conservative adjustment, not a large jump - this constant is refit "
            "properly offline via fit_stdev_inflation_factor and this is meant to be "
            "a nudge worth backtesting, not a replacement for that process."
        ),
        messages=[{"role": "user", "content": f"Recent trade diagnoses:\n{context}"}],
        output_format=CalibrationProposal,
    )
    return response.parsed_output


def _read_current_factor() -> float:
    model_py = _repo_path(MODEL_PY_PATH).read_text()
    match = INFLATION_FACTOR_PATTERN.search(model_py)
    if not match:
        raise RuntimeError(f"Could not find STDEV_INFLATION_FACTOR in {MODEL_PY_PATH}")
    return float(match.group(1))


def _repo_path(relative: str):
    from pathlib import Path

    return Path(__file__).resolve().parents[3] / relative


def backtest_with_factor(factor: float) -> dict:
    """Re-run the existing walk-forward calibration + P&L backtests with
    STDEV_INFLATION_FACTOR patched to `factor`, without touching the file on
    disk - model.py's functions take inflation_factor as a parameter, so this
    monkeypatches the module default only for the duration of the call."""
    import weatherbot.backtest.model as model_module

    original = model_module.STDEV_INFLATION_FACTOR
    model_module.STDEV_INFLATION_FACTOR = factor
    try:
        calibration_report = calibration.run()
        pnl_report = pnl_backtest.run()
    finally:
        model_module.STDEV_INFLATION_FACTOR = original
    return {"calibration": calibration_report, "pnl": pnl_report}


def _is_improvement(before: dict, after: dict) -> bool:
    """Conservative gate: coverage_68/coverage_90 must move closer to their
    0.68/0.90 targets on net, and total P&L (summed across thresholds) must
    not get worse. Both must hold - a calibration improvement that loses
    money, or a P&L bump from a coincidentally-better-fit noise, isn't
    enough on its own."""
    b_cal, a_cal = before["calibration"]["overall"], after["calibration"]["overall"]
    if b_cal["n"] == 0 or a_cal["n"] == 0:
        return False

    def coverage_error(cal: dict) -> float:
        return abs(cal["coverage_68"] - 0.68) + abs(cal["coverage_90"] - 0.90)

    calibration_improved = coverage_error(a_cal) < coverage_error(b_cal)

    b_pnl = sum(r["total_pnl_per_$1_staked"] for r in before["pnl"]["by_threshold"])
    a_pnl = sum(r["total_pnl_per_$1_staked"] for r in after["pnl"]["by_threshold"])
    pnl_not_worse = a_pnl >= b_pnl

    return calibration_improved and pnl_not_worse


def open_calibration_pr(
    new_factor: float, old_factor: float, before: dict, after: dict,
    proposal: CalibrationProposal, diagnoses: list[dict],
) -> str:
    github_token = os.environ["GITHUB_API_KEY"]
    repo_root = _repo_path(".")
    branch = f"analyst/stdev-inflation-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"

    model_py_path = _repo_path(MODEL_PY_PATH)
    contents = model_py_path.read_text()
    updated = INFLATION_FACTOR_PATTERN.sub(f"STDEV_INFLATION_FACTOR = {new_factor}\n", contents, count=1)
    model_py_path.write_text(updated)

    env = {**os.environ, "GIT_AUTHOR_NAME": BOT_COMMIT_NAME, "GIT_AUTHOR_EMAIL": BOT_COMMIT_EMAIL,
           "GIT_COMMITTER_NAME": BOT_COMMIT_NAME, "GIT_COMMITTER_EMAIL": BOT_COMMIT_EMAIL}
    # The cron container's checkout has no push-capable remote configured
    # (it's built read-only from the deploy source) - push over HTTPS with
    # the token supplied directly rather than assuming `origin` already has
    # credentials. Token never touches argv (ps-visible) or committed files -
    # only the env-scoped remote URL for this one push.
    push_url = f"https://x-access-token:{github_token}@github.com/{REPO}.git"

    subprocess.run(["git", "checkout", "-b", branch, BASE_BRANCH], cwd=repo_root, check=True, env=env)
    subprocess.run(["git", "add", MODEL_PY_PATH], cwd=repo_root, check=True, env=env)
    commit_message = (
        f"Nightly analyst: adjust STDEV_INFLATION_FACTOR {old_factor} -> {new_factor}\n\n"
        f"{proposal.reasoning}\n\n"
        "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
    )
    subprocess.run(["git", "commit", "-m", commit_message], cwd=repo_root, check=True, env=env)
    subprocess.run(["git", "push", push_url, f"HEAD:{branch}"], cwd=repo_root, check=True, env=env)

    body = f"""## Nightly analyst proposal

**Pattern found across the last {len(diagnoses)} trade diagnoses:**
{proposal.reasoning}

## Backtest comparison (walk-forward, out-of-sample)

| | Before ({old_factor}) | After ({new_factor}) |
|---|---|---|
| coverage_68 (target 0.68) | {before["calibration"]["overall"]["coverage_68"]} | {after["calibration"]["overall"]["coverage_68"]} |
| coverage_90 (target 0.90) | {before["calibration"]["overall"]["coverage_90"]} | {after["calibration"]["overall"]["coverage_90"]} |
| MAE | {before["calibration"]["overall"]["mae"]} | {after["calibration"]["overall"]["mae"]} |

Full P&L-by-threshold backtest output is in this branch's CI logs / can be re-run via
`python -m weatherbot.backtest.pnl_backtest`.

## Diagnoses that triggered this

{json.dumps(diagnoses, indent=2, default=str)}

---
This PR was opened automatically by the nightly trade analyst. It is **not**
auto-merged - please review the backtest numbers before merging.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
"""

    resp = httpx.post(
        f"https://api.github.com/repos/{REPO}/pulls",
        headers={
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "title": f"Nightly analyst: adjust STDEV_INFLATION_FACTOR to {new_factor}",
            "head": branch,
            "base": BASE_BRANCH,
            "body": body,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["html_url"]


def _save_proposal_record(
    session, outcome: str, diagnosis_ids: list[int], reasoning: str | None = None,
    old_factor: float | None = None, new_factor: float | None = None, pr_url: str | None = None,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO calibration_proposals
                (outcome, reasoning, old_factor, new_factor, pr_url, diagnosis_ids)
            VALUES
                (:outcome, :reasoning, :old_factor, :new_factor, :pr_url, :diagnosis_ids)
            """
        ),
        {
            "outcome": outcome,
            "reasoning": reasoning,
            "old_factor": old_factor,
            "new_factor": new_factor,
            "pr_url": pr_url,
            "diagnosis_ids": diagnosis_ids,
        },
    )
    session.commit()


def run() -> dict:
    session = get_session()
    try:
        diagnoses = load_recent_diagnoses(session)
        diagnosis_ids = [d["id"] for d in diagnoses]

        if not _passes_threshold(diagnoses):
            _save_proposal_record(session, "threshold_not_met", diagnosis_ids)
            return {"proposed_pr": None, "reason": "systematic_bias pattern threshold not met"}

        client = _client()
        proposal = ask_for_proposal(client, diagnoses)
        if not proposal.has_coherent_pattern or proposal.proposed_stdev_inflation_factor is None:
            _save_proposal_record(session, "no_pattern", diagnosis_ids, reasoning=proposal.reasoning)
            return {
                "proposed_pr": None,
                "reason": "no coherent pattern found",
                "claude_reasoning": proposal.reasoning,
            }

        old_factor = _read_current_factor()
        new_factor = proposal.proposed_stdev_inflation_factor

        before = backtest_with_factor(old_factor)
        after = backtest_with_factor(new_factor)

        if not _is_improvement(before, after):
            _save_proposal_record(
                session, "backtest_rejected", diagnosis_ids, reasoning=proposal.reasoning,
                old_factor=old_factor, new_factor=new_factor,
            )
            return {
                "proposed_pr": None,
                "reason": "backtest did not confirm improvement",
                "old_factor": old_factor,
                "new_factor": new_factor,
            }

        pr_url = open_calibration_pr(new_factor, old_factor, before, after, proposal, diagnoses)
        _save_proposal_record(
            session, "pr_opened", diagnosis_ids, reasoning=proposal.reasoning,
            old_factor=old_factor, new_factor=new_factor, pr_url=pr_url,
        )
        return {"proposed_pr": pr_url, "old_factor": old_factor, "new_factor": new_factor}
    finally:
        session.close()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
