import os
import sqlite3
from datetime import datetime

import pandas as pd


DB_PATH = "online_retail.db"
CSV_PATH = "Online Retail.csv"
SCHEMA_PATH = "schema.sql"


def ensure_db_and_table(db_path: str = DB_PATH, schema_path: str = SCHEMA_PATH) -> None:
    """Create SQLite database and table using schema.sql."""
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with sqlite3.connect(db_path) as conn, open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
        conn.executescript(schema_sql)


def parse_invoice_date(value):
    """Parse invoice date string to ISO format if possible, otherwise return original."""
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    text = str(value).strip()
    if not text:
        return None
    # Try common Excel/CSV datetime formats; adjust if your file uses a different format
    for fmt in ("%m/%d/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    # Fallback: return raw text
    return text


def load_csv_to_db(
    csv_path: str = CSV_PATH,
    db_path: str = DB_PATH,
) -> None:
    """Load Online Retail CSV file into SQLite database."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    print(f"Reading dataset from: {csv_path}")
    # Low-memory, chunked reading in case the file is large
    chunksize = 50_000
    total_rows = 0

    with open(csv_path, "rb") as f:
        is_excel = f.read(4) == b"PK\x03\x04"

    if is_excel:
        print("Detected Excel/OpenXML container format in data file.")
        df_all = pd.read_excel(csv_path)
        chunks = [df_all[i : i + chunksize].copy() for i in range(0, len(df_all), chunksize)]
    else:
        chunks = pd.read_csv(csv_path, chunksize=chunksize, encoding_errors="ignore")

    with sqlite3.connect(db_path) as conn:
        for chunk in chunks:
            # Normalize column names (strip spaces, make consistent)
            cols = {c: c.strip() for c in chunk.columns}
            chunk.rename(columns=cols, inplace=True)

            # Only keep the expected columns if they exist
            expected_cols = [
                "InvoiceNo",
                "StockCode",
                "Description",
                "Quantity",
                "InvoiceDate",
                "UnitPrice",
                "CustomerID",
                "Country",
            ]
            available_cols = [c for c in expected_cols if c in chunk.columns]
            chunk = chunk[available_cols]

            # Basic cleaning
            if "Quantity" in chunk.columns:
                chunk["Quantity"] = pd.to_numeric(chunk["Quantity"], errors="coerce")
            if "UnitPrice" in chunk.columns:
                chunk["UnitPrice"] = pd.to_numeric(chunk["UnitPrice"], errors="coerce")

            if "InvoiceDate" in chunk.columns:
                chunk["InvoiceDate"] = chunk["InvoiceDate"].apply(parse_invoice_date)

            # Write to database
            chunk.to_sql("online_retail", conn, if_exists="append", index=False)
            total_rows += len(chunk)
            print(f"Inserted {len(chunk)} rows (total so far: {total_rows})")

    print(f"Finished loading data. Total rows inserted: {total_rows}")


if __name__ == "__main__":
    ensure_db_and_table()
    load_csv_to_db()



