import pandas as pd

SYSTEM_PROMPT = """You are an expert Account Executive coach preparing a sales professional for a customer meeting.
Be concise, opinionated, and specific to this account — never generic.
Speak directly to the AE: use "you should", "ask them about", "avoid".
Structure your response in exactly these sections:
**Situation** (2 sentences): current state of the account.
**Top priority**: the single most important thing to accomplish in this meeting.
**Talking points** (3 bullets): account-specific, not generic.
**Watch out for**: one risk or objection to prepare for.
**Suggested ask**: one concrete commitment to request before the call ends."""


# ── Signal interpreters ───────────────────────────────────────────────────────


def _renewal_context(days: int) -> str:
    """Classify renewal urgency into actionable bands for the AE."""
    if days <= 30:
        return "imminent — contract expires in less than a month"
    if days <= 60:
        return "close — renewal conversation should already be underway"
    if days <= 90:
        return "approaching — begin renewal preparation now"
    return "not yet urgent"


def _ticket_context(count: int) -> str:
    """Classify open ticket volume relative to the scorer's 99th-percentile cap (~13).

    Thresholds are set at roughly one-third (~4) and two-thirds (~9) of that cap
    so the bands reflect the same scale used to compute the risk score.
    """
    if count >= 9:
        return "high — a significant pain point, expect this to come up"
    if count >= 4:
        return "elevated — likely affecting satisfaction"
    return "minor friction — worth checking status before the call"


def _inactivity_context(days: int) -> str | None:
    """Interpret sales inactivity using the scorer's continuous inactivity signal (0.25 weight).

    The scorer normalises days against the dataset maximum (~180 days). Thresholds here
    reflect meaningful points on that scale: 45 days (~25% of max) is when the signal
    starts contributing noticeably; 90 days (~50% of max) is when it becomes significant.
    Returns None when inactivity is below the actionable threshold.
    """
    if days >= 90:
        return f"→ No sales contact in {days} days — account may feel neglected going into renewal."
    if days >= 45:
        return f"→ Last contact {days} days ago — worth scheduling a check-in soon."
    return None


def _ai_adoption_context(score: float) -> str:
    """Interpret AI adoption using the scorer's continuous 0–1 scale (0.35 weight).

    Bands are set at one-third (0.33) and two-thirds (0.66) of the scale so they
    reflect the same proportional contribution as in the opportunity score.
    """
    if score >= 0.66:
        return "strong — account is actively realizing product value"
    if score >= 0.33:
        return "moderate — room to deepen feature adoption"
    return "low — limited value realization, a retention and expansion risk"


# ── Prompt sections ───────────────────────────────────────────────────────────


def _company_context(account: pd.Series, uplift_str: str) -> list[str]:
    """Part 1 — who the account is and their current financial position."""
    return [
        f"Account: {account['account_name']}",
        f"What they do: {account['account_description']}",
        f"Industry: {account['industry']} | Segment: {account['segment']} | Region: {account['region']}",
        f"Current ARR: ${account['current_revenue']:,.0f} → Projected: ${account['revenue_end_of_quarter']:,.0f} ({uplift_str})",
        "",
    ]


def _risk_summary(account: pd.Series, uplift_pct: float) -> list[str]:
    """Part 2a — recommended action, risk label, and only the signals that fired."""
    renewal_days = int(account["days_to_next_renewal"])
    lines = [
        f"Recommended action: {account['primary_action']}",
        f"Risk: {account['risk_label']} (score {account['risk_score']}/100)",
        f"→ Renewal in {renewal_days} days ({_renewal_context(renewal_days)})",
    ]

    inactivity = _inactivity_context(int(account["days_since_last_sales_activity"]))
    if inactivity:
        lines.append(inactivity)

    if account["nr_support_tickets"] > 0:
        tickets = int(account["nr_support_tickets"])
        lines.append(f"→ {tickets} open support tickets ({_ticket_context(tickets)})")

    if account["contraction_signal"]:
        lines.append(
            f"→ Revenue projected to decline by {abs(uplift_pct):.0%}"
            f" (from ${account['current_revenue']:,.0f} to ${account['revenue_end_of_quarter']:,.0f})"
        )

    if account["seat_utilization"] < 0.50:
        lines.append(
            f"→ {account['seat_utilization']:.0%} seat utilization"
            f" — {int(account['unused_seats'])} seats unused"
        )
    return lines


def _opportunity_summary(account: pd.Series, uplift_pct: float) -> list[str]:
    """Part 2b — opportunity label and only the signals that fired.

    Activation thresholds mirror the scorer: low_coverage fires below 25%
    license_coverage, seat_saturation fires above 75% utilization.
    """
    lines = [
        "",
        f"Opportunity: {account['opportunity_label']} (score {account['opportunity_score']}/100)",
    ]

    if account["expansion_signal"]:
        lines.append(f"→ ARR projected to grow by {abs(uplift_pct):.0%}")

    if account["seat_utilization"] > 0.75:
        lines.append(
            f"→ {account['seat_utilization']:.0%} seat utilization — account is near capacity"
        )

    lines.append(
        f"→ AI adoption: {account['ai_usage']:.0%} ({_ai_adoption_context(account['ai_usage'])})"
    )

    if account["license_coverage"] < 0.25:
        lines.append(
            f"→ License coverage: {account['license_coverage']:.0%}"
            f" — most employees are not yet licensed, meaningful expansion room exists"
        )
    return lines


def _last_call(account: pd.Series) -> list[str]:
    """Part 3 — most recent call transcript for context, if one exists."""
    if account["has_transcript"]:
        days = int(account["days_since_last_sales_activity"])
        return [
            "",
            f"Last call ({days} days ago): {account['call_transcript_summary']}",
        ]
    return ["", "No recent call on record."]


def build_prompt(account: pd.Series) -> tuple[str, str]:
    """Assemble (system_prompt, user_message) for the meeting brief.

    Sends derived signals consistent with the UI — not raw columns. Conditional
    blocks ensure the prompt reflects only the signals that actually fired for
    this account, so a Protect account and a Grow account receive meaningfully
    different context.
    """
    uplift_pct = account["arr_uplift"] - 1
    uplift_str = (
        f"+{uplift_pct:.0%}"
        if account["expansion_signal"]
        else (f"{uplift_pct:.0%}" if account["contraction_signal"] else "flat")
    )

    lines = (
        _company_context(account, uplift_str)
        + _risk_summary(account, uplift_pct)
        + _opportunity_summary(account, uplift_pct)
        + _last_call(account)
    )

    return SYSTEM_PROMPT, "\n".join(lines)
