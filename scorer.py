import pandas as pd
from data_loader import load_accounts


def risk_score(
    row: pd.Series,
    staleness_max: float,
    renewal_max: float,
    ticket_cap: float,
) -> float:
    """Return a 0–100 risk score indicating churn or revenue-loss likelihood."""
    renewal = max(0, 1 - row["days_to_next_renewal"] / renewal_max)
    staleness = min(1, row["days_since_last_sales_activity"] / staleness_max)
    tickets = min(1, row["nr_support_tickets"] / ticket_cap)
    utilization = max(0, 0.5 - row["seat_utilization"]) * 2
    contraction = max(0, 1 - row["arr_uplift"])

    return round((renewal * 0.30 + staleness * 0.25 + tickets * 0.20 + utilization * 0.15 + contraction * 0.10) * 100, 1)


def opportunity_score(row: pd.Series, arr_uplift_scale: float) -> float:
    """Return a 0–100 opportunity score indicating expansion readiness."""
    arr_uplift = min(1, (row["arr_uplift"] - 1) / arr_uplift_scale)
    ai = row["ai_usage"]
    # 0.75 is the activation threshold (accounts using >75% of seats are expansion candidates);
    # 0.25 is the range above that threshold, normalizing the bonus to 0–1
    seat_saturation = max(0, row["seat_utilization"] - 0.75) / 0.25
    # 0.25 is the activation ceiling (accounts with <25% penetration have meaningful whitespace);
    # 0.25 is the range below that ceiling, normalizing the bonus to 0–1
    seat_whitespace = max(0, 0.25 - row["seat_penetration"]) / 0.25

    return round((ai * 0.35 + arr_uplift * 0.25 + seat_saturation * 0.25 + seat_whitespace * 0.15) * 100, 1)


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


def score_accounts(df: pd.DataFrame) -> pd.DataFrame:
    """Add risk, opportunity, and attention scores and labels to the accounts DataFrame."""
    # Data-derived normalization parameters
    staleness_max = df["days_since_last_sales_activity"].max()
    renewal_max = df["days_to_next_renewal"].max()
    ticket_cap = df["nr_support_tickets"].quantile(0.99)
    arr_uplift_scale = df["arr_uplift"].max() - 1

    df = df.copy()
    df["risk_score"] = df.apply(
        lambda row: risk_score(row, staleness_max, renewal_max, ticket_cap), axis=1
    )
    df["opportunity_score"] = df.apply(
        lambda row: opportunity_score(row, arr_uplift_scale), axis=1
    )
    df["attention_score"] = round(df["risk_score"] * 0.6 + df["opportunity_score"] * 0.4, 1)
    df["risk_label"] = df["risk_score"].apply(risk_label)
    df["opportunity_label"] = df["opportunity_score"].apply(opportunity_label)
    return df


if __name__ == "__main__":
    df = score_accounts(load_accounts())
    top10 = df.nlargest(10, "attention_score")[
        ["account_name", "attention_score", "risk_score", "risk_label", "opportunity_score", "opportunity_label"]
    ]
    print(top10.to_string(index=False))
