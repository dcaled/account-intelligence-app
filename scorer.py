import pandas as pd
from data_loader import load_accounts


def risk_score(
    row: pd.Series,
    inactivity_max: float,
    renewal_max: float,
    ticket_cap: float,
) -> float:
    """Return a 0–100 risk score indicating churn or revenue-loss likelihood."""
    renewal = 1 - row["days_to_next_renewal"] / renewal_max
    inactivity = row["days_since_last_sales_activity"] / inactivity_max
    tickets = min(1, row["nr_support_tickets"] / ticket_cap)
    utilization = max(0, 0.5 - row["seat_utilization"]) * 2
    arr_contraction = max(0, 1 - row["arr_uplift"])

    return round(
        max(
            0.0,
            (
                renewal * 0.30
                + inactivity * 0.25
                + tickets * 0.20
                + utilization * 0.15
                + arr_contraction * 0.10
            ),
        )
        * 100,
        1,
    )


def opportunity_score(row: pd.Series, arr_uplift_scale: float) -> float:
    """Return a 0–100 opportunity score indicating expansion readiness."""
    arr_uplift = max(0, (row["arr_uplift"] - 1) / arr_uplift_scale)
    ai = row["ai_usage"]
    # 0.75 is the activation threshold (accounts using >75% of seats are expansion candidates);
    # 0.25 is the range above that threshold, normalizing the bonus to 0–1
    seat_saturation = max(0, row["seat_utilization"] - 0.75) / 0.25
    # 0.25 is the activation ceiling (accounts with <25% license coverage have meaningful
    # expansion room); 0.25 is the range below that ceiling, normalizing the bonus to 0–1
    low_coverage = max(0, 0.25 - row["license_coverage"]) / 0.25

    return round(
        max(
            0.0,
            (
                ai * 0.35
                + arr_uplift * 0.25
                + seat_saturation * 0.25
                + low_coverage * 0.15
            ),
        )
        * 100,
        1,
    )


def risk_label(score: float) -> str:
    """Map a risk score to a human-readable label."""
    if score >= 50:
        return "At Risk"
    if score >= 30:
        return "Needs Check-in"
    return "Healthy"


def opportunity_label(score: float) -> str:
    """Map an opportunity score to a human-readable label."""
    if score >= 70:
        return "Expansion Ready"
    if score >= 40:
        return "Growth Signal"
    return "Stable"


def primary_action(risk: str, opportunity: str) -> str:
    """Derive a single AE directive from the combination of risk and opportunity labels.

    Risk takes precedence: an at-risk account must be protected regardless of expansion signals.
    When risk is neutral the opportunity label drives the action.
    """
    if risk == "At Risk":
        return "Protect"
    if risk == "Needs Check-in" and opportunity == "Expansion Ready":
        return "Check-in + Expand"
    if risk == "Needs Check-in":
        return "Check-in"
    if opportunity == "Expansion Ready":
        return "Expand"
    if opportunity == "Growth Signal":
        return "Grow"
    return "Monitor"


def score_accounts(df: pd.DataFrame) -> pd.DataFrame:
    """Add risk, opportunity, attention scores, labels, and primary action to the accounts DataFrame."""
    # Data-derived normalization parameters
    inactivity_max = df["days_since_last_sales_activity"].max()
    renewal_max = df["days_to_next_renewal"].max()
    ticket_cap = df["nr_support_tickets"].quantile(0.99)
    arr_uplift_scale = df["arr_uplift"].max() - 1

    df = df.copy()
    df["risk_score"] = df.apply(
        lambda row: risk_score(row, inactivity_max, renewal_max, ticket_cap), axis=1
    )
    df["opportunity_score"] = df.apply(
        lambda row: opportunity_score(row, arr_uplift_scale), axis=1
    )
    df["attention_score"] = round(
        df["risk_score"] * 0.6 + df["opportunity_score"] * 0.4, 1
    )
    df["risk_label"] = df["risk_score"].apply(risk_label)
    df["opportunity_label"] = df["opportunity_score"].apply(opportunity_label)
    df["primary_action"] = df.apply(
        lambda row: primary_action(row["risk_label"], row["opportunity_label"]), axis=1
    )
    return df


if __name__ == "__main__":
    df = score_accounts(load_accounts())
    top10 = df.nlargest(10, "attention_score")[
        [
            "account_name",
            "attention_score",
            "risk_score",
            "risk_label",
            "opportunity_score",
            "opportunity_label",
        ]
    ]
    print(top10.to_string(index=False))
