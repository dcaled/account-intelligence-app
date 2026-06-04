import pandas as pd
from pathlib import Path

DATA_PATH = Path(__file__).parent / "account_data.csv"


def load_accounts() -> pd.DataFrame:
    """Load accounts CSV, fill nulls, and add derived columns seat_utilization and arr_uplift."""
    df = pd.read_csv(DATA_PATH)

    # Null handling — fill missing inactivity with the observed max (worst case, data-driven)
    inactivity_max = df["days_since_last_sales_activity"].max()
    df["days_since_last_sales_activity"] = df["days_since_last_sales_activity"].fillna(
        inactivity_max
    )
    df["region"] = df["region"].fillna("Unknown").replace("", "Unknown")
    df["ai_usage"] = df["ai_usage"].fillna(0.0).clip(lower=0.0, upper=1.0)

    # Derived columns
    df["seat_utilization"] = df["nr_active_users"] / df["nr_licensed_seats"]
    df["license_coverage"] = (df["nr_licensed_seats"] / df["nr_employees"]).clip(
        upper=1.0
    )
    df["arr_uplift"] = df["revenue_end_of_quarter"] / df["current_revenue"]
    df["unused_seats"] = df["nr_licensed_seats"] - df["nr_active_users"]
    df["expansion_signal"] = df["revenue_end_of_quarter"] > df["current_revenue"]
    df["contraction_signal"] = df["revenue_end_of_quarter"] < df["current_revenue"]
    df["has_transcript"] = df["call_transcript_summary"].notna() & df[
        "call_transcript_summary"
    ].str.strip().ne("")

    return df


if __name__ == "__main__":
    df = load_accounts()
    print(f"Loaded {len(df)} accounts")
    print(
        df[
            [
                "account_name",
                "seat_utilization",
                "arr_uplift",
                "expansion_signal",
                "contraction_signal",
            ]
        ].head(10)
    )
