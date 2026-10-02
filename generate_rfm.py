"""
Customer RFM Segmentation Script
Queries SQLite database for Online Retail data, calculates RFM metrics,
assigns quartile scores using SQL window functions (NTILE(4)),
and exports results to CSV.

Author: Jatin Choudhary
"""

import os
import sqlite3
from pathlib import Path
import pandas as pd

# Paths
DB_FILENAME = "online_retail.db"
OUTPUT_FILENAME = "rfm_customer_segments.csv"


def locate_db() -> Path:
    """Locate online_retail.db in current directory or child directory."""
    candidates = [
        Path(DB_FILENAME),
        Path("Online-Retail-SQL-main") / DB_FILENAME,
        Path(__file__).parent / DB_FILENAME,
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Database '{DB_FILENAME}' not found. Please run load_data.py first."
    )


def compute_rfm(db_path: Path) -> pd.DataFrame:
    """
    Execute SQL query with NTILE(4) window functions to compute RFM segments.
    """
    rfm_query = """
    WITH max_reference_date AS (
        SELECT MAX(InvoiceDate) AS max_tx_date
        FROM online_retail
    ),
    customer_metrics AS (
        SELECT
            CASE 
                WHEN CustomerID LIKE '%.0' THEN SUBSTR(CustomerID, 1, LENGTH(CustomerID) - 2)
                ELSE CustomerID
            END AS customer_id,
            MAX(InvoiceDate) AS last_order_date,
            CAST(ROUND(JULIANDAY((SELECT max_tx_date FROM max_reference_date)) - JULIANDAY(MAX(InvoiceDate))) AS INTEGER) AS recency_days,
            COUNT(DISTINCT InvoiceNo) AS frequency,
            ROUND(SUM(Quantity * UnitPrice), 2) AS monetary
        FROM online_retail
        WHERE CustomerID IS NOT NULL
          AND CustomerID != ''
          AND InvoiceNo NOT LIKE 'C%'
          AND Quantity > 0
          AND UnitPrice > 0
        GROUP BY CustomerID
    ),
    rfm_quartiles AS (
        SELECT
            customer_id,
            last_order_date,
            recency_days,
            frequency,
            monetary,
            -- Recency: fewer days since last order is better; ordering DESC gives 4 to the lowest recency days
            NTILE(4) OVER (ORDER BY recency_days DESC) AS r_score,
            -- Frequency: more orders is better; ordering ASC gives 4 to highest frequency
            NTILE(4) OVER (ORDER BY frequency ASC) AS f_score,
            -- Monetary: higher spend is better; ordering ASC gives 4 to highest spend
            NTILE(4) OVER (ORDER BY monetary ASC) AS m_score
        FROM customer_metrics
    )
    SELECT
        customer_id,
        last_order_date,
        recency_days,
        frequency,
        monetary,
        r_score,
        f_score,
        m_score,
        (r_score + f_score + m_score) AS rfm_total_score,
        CAST(r_score AS TEXT) || CAST(f_score AS TEXT) || CAST(m_score AS TEXT) AS rfm_segment,
        CASE
            WHEN r_score = 4 AND f_score = 4 AND m_score = 4 THEN 'Champions'
            WHEN r_score >= 3 AND f_score >= 3 AND m_score >= 3 THEN 'Loyal Customers'
            WHEN r_score >= 3 AND f_score >= 3 THEN 'Active Buyers'
            WHEN r_score >= 3 AND f_score <= 2 AND m_score >= 3 THEN 'High-Value Recent'
            WHEN r_score = 4 AND f_score = 1 THEN 'New Customers'
            WHEN r_score = 3 AND f_score <= 2 THEN 'Potential Loyalists'
            WHEN r_score <= 2 AND f_score >= 3 AND m_score >= 3 THEN 'At Risk (High Value)'
            WHEN r_score <= 2 AND f_score >= 3 THEN 'Need Attention'
            WHEN r_score = 2 AND f_score <= 2 THEN 'About to Sleep'
            WHEN r_score = 1 AND f_score = 1 THEN 'Lost / Inactive'
            ELSE 'Standard'
        END AS segment_label
    FROM rfm_quartiles
    ORDER BY rfm_total_score DESC, monetary DESC;
    """

    print(f"Connecting to database: {db_path.resolve()}")
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(rfm_query, conn)
    return df


def main():
    db_path = locate_db()
    output_path = db_path.parent / OUTPUT_FILENAME

    print("=" * 70)
    print("CUSTOMER RFM SEGMENTATION ANALYSIS (NTILE QUARTILES)")
    print("=" * 70)

    df_rfm = compute_rfm(db_path)
    total_customers = len(df_rfm)
    print(f"\n[OK] Successfully calculated RFM metrics for {total_customers:,} unique customers.")

    # Export to CSV
    df_rfm.to_csv(output_path, index=False)
    print(f"[OK] Exported segments to: {output_path.resolve()}")

    # Preview summary
    print("\n" + "=" * 70)
    print("TOP 10 HIGH-VALUE CUSTOMERS (SAMPLE)")
    print("=" * 70)
    print(df_rfm[["customer_id", "recency_days", "frequency", "monetary", "r_score", "f_score", "m_score", "rfm_segment", "segment_label"]].head(10).to_string(index=False))

    print("\n" + "=" * 70)
    print("RFM SEGMENT DISTRIBUTION SUMMARY")
    print("=" * 70)
    summary = df_rfm.groupby("segment_label").agg(
        customer_count=("customer_id", "count"),
        avg_recency_days=("recency_days", "mean"),
        avg_frequency=("frequency", "mean"),
        total_revenue=("monetary", "sum"),
        avg_spend=("monetary", "mean"),
    ).round(2).sort_values("customer_count", ascending=False)

    summary["pct_customers"] = ((summary["customer_count"] / total_customers) * 100).round(1).astype(str) + "%"
    print(summary[["customer_count", "pct_customers", "avg_recency_days", "avg_frequency", "avg_spend", "total_revenue"]].to_string())

    print("\n" + "=" * 70)
    print(f"COMPLETE: '{OUTPUT_FILENAME}' generated successfully with {len(df_rfm):,} rows.")
    print("=" * 70)


if __name__ == "__main__":
    main()
