import pandas as pd
from pathlib import Path

DATA_PATH = Path(__file__).parent / "account_data.csv"


def load_accounts() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)

    # Null handling
    df["days_since_last_sales_activity"] = df["days_since_last_sales_activity"].fillna(120)
    df["region"] = df["region"].fillna("Unknown").replace("", "Unknown")
    df["ai_usage"] = df["ai_usage"].fillna(0.0)

    # Derived columns
    df["seat_utilization"] = df["nr_active_users"] / df["nr_licensed_seats"]
    df["revenue_uplift"] = df["revenue_end_of_quarter"] / df["current_revenue"]

    return df


if __name__ == "__main__":
    df = load_accounts()
    print(f"Loaded {len(df)} accounts")
    print(df[["account_name", "seat_utilization", "revenue_uplift"]].head(10))
