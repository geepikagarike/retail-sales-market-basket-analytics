"""Clean the UCI Online Retail CSV without modifying the source file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

REQUIRED_COLUMNS = {
    "InvoiceNo",
    "StockCode",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
}
OPTIONAL_COLUMNS = {"Description", "CustomerID", "Country"}
CSV_ENCODINGS = ("utf-8-sig", "cp1252")


def read_retail_csv(input_path: Path) -> pd.DataFrame:
    """Read the Kaggle/UCI CSV, including the common Windows-1252 encoding."""
    errors: list[str] = []
    for encoding in CSV_ENCODINGS:
        try:
            return pd.read_csv(
                input_path,
                encoding=encoding,
                dtype={
                    "InvoiceNo": "string",
                    "StockCode": "string",
                    "CustomerID": "string",
                },
                low_memory=False,
            )
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
    raise ValueError(
        f"Could not decode {input_path} using supported encodings: {'; '.join(errors)}"
    )


def clean_transactions(input_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Clean invoice lines while retaining valid returns and unknown customers.

    Positive quantities are eligible for baskets. Negative quantities represent
    returns: they remain in the cleaned sales data and net sales, but are not
    treated as purchased items in market-basket analysis.
    """
    raw = read_retail_csv(input_path)
    missing_columns = REQUIRED_COLUMNS.difference(raw.columns)
    if missing_columns:
        raise ValueError(f"Input is missing required columns: {', '.join(sorted(missing_columns))}")

    for column in OPTIONAL_COLUMNS.difference(raw.columns):
        raw[column] = pd.NA

    original_count = len(raw)
    frame = raw.copy()
    frame["InvoiceNo"] = frame["InvoiceNo"].astype("string").str.strip()
    frame["StockCode"] = frame["StockCode"].astype("string").str.strip()
    frame["Description"] = frame["Description"].astype("string").str.strip()
    frame["CustomerID"] = frame["CustomerID"].astype("string").str.strip()
    frame["Country"] = frame["Country"].astype("string").str.strip()
    frame["Quantity"] = pd.to_numeric(frame["Quantity"], errors="coerce")
    frame["UnitPrice"] = pd.to_numeric(frame["UnitPrice"], errors="coerce")
    frame["InvoiceDate"] = pd.to_datetime(frame["InvoiceDate"], errors="coerce", format="mixed")

    dropped: dict[str, int] = {}

    def discard(mask: pd.Series, reason: str) -> None:
        nonlocal frame
        dropped[reason] = int(mask.sum())
        frame = frame.loc[~mask].copy()

    discard(
        frame["InvoiceNo"].isna()
        | frame["InvoiceNo"].eq("")
        | frame["StockCode"].isna()
        | frame["StockCode"].eq(""),
        "missing_invoice_or_product_id",
    )
    discard(frame["InvoiceNo"].str.upper().str.startswith("C", na=False), "cancelled_invoice")
    duplicate_columns = list(raw.columns)
    discard(frame.duplicated(subset=duplicate_columns, keep="first"), "duplicate_row")
    discard(
        frame["InvoiceDate"].isna()
        | frame["Quantity"].isna()
        | frame["UnitPrice"].isna(),
        "invalid_date_or_numeric_value",
    )
    discard(frame["Quantity"].eq(0), "zero_quantity")
    discard(frame["UnitPrice"].le(0), "non_positive_unit_price")

    frame["SalesAmount"] = frame["Quantity"] * frame["UnitPrice"]
    frame["TransactionType"] = frame["Quantity"].map(
        lambda quantity: "Sale" if quantity > 0 else "Return"
    )
    frame = frame.sort_values(["InvoiceDate", "InvoiceNo", "StockCode"]).reset_index(drop=True)
    report: dict[str, Any] = {
        "source_file": input_path.name,
        "rows_before": original_count,
        "rows_after": len(frame),
        "rows_dropped_by_reason": dropped,
        "rows_retained_as_returns": int(frame["Quantity"].lt(0).sum()),
        "rows_eligible_for_market_basket": int(frame["Quantity"].gt(0).sum()),
        "missing_descriptions_retained": int(frame["Description"].isna().sum()),
        "missing_customer_ids_retained": int(frame["CustomerID"].isna().sum()),
        "missing_countries_retained": int(frame["Country"].isna().sum()),
        "distinct_invoices_after_cleaning": int(frame["InvoiceNo"].nunique()),
        "distinct_products_after_cleaning": int(frame["StockCode"].nunique()),
        "sales_amount_definition": "Quantity * UnitPrice; positive sales and non-cancelled returns retained",
        "market_basket_definition": "distinct StockCode values per InvoiceNo, using positive-quantity lines only",
        "cleaning_rules": [
            "Exclude rows missing InvoiceNo or StockCode; Description, CustomerID, and Country are optional.",
            "Exclude cancelled invoices identified by InvoiceNo beginning with C, case-insensitively.",
            "Remove rows identical across normalized source columns, keeping the first occurrence.",
            "Exclude unparseable dates, quantities, and unit prices.",
            "Exclude zero quantities and non-positive unit prices.",
            "Keep negative quantities as returns for net sales; exclude them from baskets.",
        ],
    }
    return frame, report


def _write_json(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=project_root / "data" / "raw" / "Online_Retail.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "data" / "processed" / "cleaned_online_retail.csv",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace existing output files.")
    args = parser.parse_args()
    report_path = args.output.with_name("data_quality_report.json")
    existing = [path for path in (args.output, report_path) if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing output(s): {', '.join(map(str, existing))}. "
            "Inspect them or pass --overwrite."
        )
    if not args.input.is_file():
        raise FileNotFoundError(f"Input CSV not found: {args.input}")

    cleaned, report = clean_transactions(args.input)
    if cleaned.empty:
        raise ValueError("No usable retail records remained after cleaning.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(args.output, index=False, encoding="utf-8-sig")
    _write_json(report, report_path)
    print(
        f"Cleaned {report['rows_after']:,} of {report['rows_before']:,} rows; "
        f"retained {report['rows_retained_as_returns']:,} returns. "
        f"Saved data to {args.output} and report to {report_path}"
    )


if __name__ == "__main__":
    main()
