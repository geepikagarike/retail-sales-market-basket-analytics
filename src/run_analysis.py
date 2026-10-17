"""Generate sales and invoice-level market-basket results from cleaned retail data."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .data_preprocessing import clean_transactions
from .market_basket import apriori, association_rules, fpgrowth

OUTPUT_FILES = (
    "sales_summary.csv",
    "sales_by_month.csv",
    "sales_by_country.csv",
    "sales_by_product.csv",
    "frequent_itemsets_apriori.csv",
    "frequent_itemsets_fpgrowth.csv",
    "association_rules_apriori.csv",
    "association_rules_fpgrowth.csv",
    "algorithm_comparison.csv",
    "sales_by_month.png",
    "top_products_by_sales.png",
    "algorithm_comparison.png",
)


def _sales_outputs(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    sales = frame.copy()
    sales["GrossSalesAmount"] = sales["SalesAmount"].where(sales["Quantity"].gt(0), 0)
    sales["ReturnAmount"] = (-sales["SalesAmount"]).where(sales["Quantity"].lt(0), 0)
    sales["SalesUnits"] = sales["Quantity"].where(sales["Quantity"].gt(0), 0)
    sales["ReturnUnits"] = (-sales["Quantity"]).where(sales["Quantity"].lt(0), 0)

    summary = pd.DataFrame(
        [
            {
                "cleaned_invoice_lines": len(sales),
                "distinct_invoices": sales["InvoiceNo"].nunique(),
                "distinct_products": sales["StockCode"].nunique(),
                "known_customers": sales["CustomerID"].nunique(),
                "sale_lines": int(sales["Quantity"].gt(0).sum()),
                "return_lines": int(sales["Quantity"].lt(0).sum()),
                "gross_sales_amount": sales["GrossSalesAmount"].sum(),
                "returned_amount": sales["ReturnAmount"].sum(),
                "net_sales_amount": sales["SalesAmount"].sum(),
                "units_sold": sales["SalesUnits"].sum(),
                "units_returned": sales["ReturnUnits"].sum(),
            }
        ]
    )

    sales["Month"] = sales["InvoiceDate"].dt.to_period("M").astype(str)
    by_month = (
        sales.groupby("Month", as_index=False)
        .agg(
            net_sales_amount=("SalesAmount", "sum"),
            gross_sales_amount=("GrossSalesAmount", "sum"),
            returned_amount=("ReturnAmount", "sum"),
            units_sold=("SalesUnits", "sum"),
            units_returned=("ReturnUnits", "sum"),
            invoice_count=("InvoiceNo", "nunique"),
        )
        .sort_values("Month")
    )

    sales["Country"] = sales["Country"].fillna("").replace("", "Unknown")
    by_country = (
        sales.groupby("Country", as_index=False)
        .agg(
            net_sales_amount=("SalesAmount", "sum"),
            gross_sales_amount=("GrossSalesAmount", "sum"),
            returned_amount=("ReturnAmount", "sum"),
            invoice_count=("InvoiceNo", "nunique"),
        )
        .sort_values("net_sales_amount", ascending=False)
    )

    by_product = (
        sales.groupby("StockCode", as_index=False)
        .agg(
            description=(
                "Description",
                lambda values: next((value for value in values if pd.notna(value)), ""),
            ),
            net_sales_amount=("SalesAmount", "sum"),
            gross_sales_amount=("GrossSalesAmount", "sum"),
            returned_amount=("ReturnAmount", "sum"),
            units_sold=("SalesUnits", "sum"),
            units_returned=("ReturnUnits", "sum"),
            invoice_count=("InvoiceNo", "nunique"),
        )
        .sort_values("net_sales_amount", ascending=False)
    )
    return {
        "sales_summary": summary,
        "sales_by_month": by_month,
        "sales_by_country": by_country,
        "sales_by_product": by_product,
    }


def _write_itemsets(
    itemsets: dict[frozenset[str], int], transaction_count: int, path: Path
) -> None:
    rows = [
        {
            "itemset": " | ".join(sorted(items)),
            "itemset_size": len(items),
            "support_count": count,
            "support": count / transaction_count,
        }
        for items, count in itemsets.items()
    ]
    columns = ["itemset", "itemset_size", "support_count", "support"]
    result = pd.DataFrame(rows, columns=columns)
    if not result.empty:
        result = result.sort_values(
            ["itemset_size", "support_count", "itemset"],
            ascending=[True, False, True],
        )
    result.to_csv(path, index=False, encoding="utf-8-sig")


def _write_chart_files(
    monthly: pd.DataFrame, products: pd.DataFrame, comparison: pd.DataFrame, output_dir: Path
) -> None:
    figure, axis = plt.subplots(figsize=(10, 5))
    axis.plot(monthly["Month"], monthly["net_sales_amount"], marker="o", color="#008c95")
    axis.set_title("Monthly net sales")
    axis.set_xlabel("Month")
    axis.set_ylabel("Net sales amount")
    axis.tick_params(axis="x", labelrotation=45)
    figure.tight_layout()
    figure.savefig(output_dir / "sales_by_month.png", dpi=150)
    plt.close(figure)

    top_products = products.head(10).sort_values("net_sales_amount")
    labels = top_products["StockCode"].astype(str) + " - " + top_products["description"].astype(str)
    figure, axis = plt.subplots(figsize=(10, 6))
    axis.barh(labels, top_products["net_sales_amount"], color="#008c95")
    axis.set_title("Top 10 products by net sales")
    axis.set_xlabel("Net sales amount")
    figure.tight_layout()
    figure.savefig(output_dir / "top_products_by_sales.png", dpi=150)
    plt.close(figure)

    figure, axes = plt.subplots(1, 2, figsize=(9, 4))
    axes[0].bar(comparison["algorithm"], comparison["frequent_itemsets"], color="#008c95")
    axes[0].set_title("Frequent itemsets")
    axes[0].set_ylabel("Count")
    axes[1].bar(comparison["algorithm"], comparison["runtime_seconds"], color="#173650")
    axes[1].set_title("Runtime (same baskets and thresholds)")
    axes[1].set_ylabel("Seconds")
    figure.tight_layout()
    figure.savefig(output_dir / "algorithm_comparison.png", dpi=150)
    plt.close(figure)


def run(
    input_path: Path,
    output_dir: Path,
    min_support: float,
    min_confidence: float,
    overwrite: bool = False,
) -> None:
    if not 0 < min_support <= 1:
        raise ValueError("min_support must be greater than 0 and at most 1.")
    if not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be between 0 and 1.")
    if not input_path.is_file():
        raise FileNotFoundError(f"Cleaned input CSV not found: {input_path}")
    existing = [output_dir / name for name in OUTPUT_FILES if (output_dir / name).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing output(s): {', '.join(map(str, existing))}. "
            "Inspect them or pass --overwrite."
        )

    cleaned = pd.read_csv(
        input_path,
        encoding="utf-8-sig",
        dtype={"InvoiceNo": "string", "StockCode": "string", "CustomerID": "string"},
        parse_dates=["InvoiceDate"],
    )
    required = {"InvoiceNo", "StockCode", "Quantity", "UnitPrice", "InvoiceDate"}
    missing = required.difference(cleaned.columns)
    if missing:
        raise ValueError(f"Cleaned input is missing required columns: {', '.join(sorted(missing))}")
    if cleaned.empty:
        raise ValueError("Cleaned input contains no rows.")

    output_dir.mkdir(parents=True, exist_ok=True)
    sales = _sales_outputs(cleaned)
    for name, dataframe in sales.items():
        dataframe.to_csv(output_dir / f"{name}.csv", index=False, encoding="utf-8-sig")

    positive_lines = cleaned.loc[cleaned["Quantity"].gt(0)]
    baskets = [
        sorted(set(group["StockCode"].dropna().astype(str)))
        for _, group in positive_lines.groupby("InvoiceNo", sort=True)
    ]
    baskets = [basket for basket in baskets if basket]
    if not baskets:
        raise ValueError("No positive-quantity invoice baskets remain for market-basket analysis.")

    algorithm_results = []
    for name, algorithm in (("apriori", apriori), ("fpgrowth", fpgrowth)):
        started = time.perf_counter()
        itemsets = algorithm(baskets, min_support)
        elapsed = time.perf_counter() - started
        rules = association_rules(itemsets, len(baskets), min_confidence)
        _write_itemsets(
            itemsets,
            len(baskets),
            output_dir / f"frequent_itemsets_{name}.csv",
        )
        pd.DataFrame(
            rules,
            columns=[
                "antecedent",
                "consequent",
                "support_count",
                "support",
                "confidence",
                "lift",
            ],
        ).to_csv(
            output_dir / f"association_rules_{name}.csv",
            index=False,
            encoding="utf-8-sig",
        )
        algorithm_results.append(
            {
                "algorithm": name,
                "transactions": len(baskets),
                "frequent_itemsets": len(itemsets),
                "association_rules": len(rules),
                "runtime_seconds": elapsed,
                "min_support": min_support,
                "min_confidence": min_confidence,
            }
        )

    comparison = pd.DataFrame(algorithm_results)
    comparison.to_csv(output_dir / "algorithm_comparison.csv", index=False, encoding="utf-8-sig")
    _write_chart_files(
        sales["sales_by_month"],
        sales["sales_by_product"],
        comparison,
        output_dir,
    )
    print(
        f"Analyzed {len(cleaned):,} cleaned lines and {len(baskets):,} positive-purchase "
        f"invoices; wrote sales summaries, itemsets, rules, comparison, and charts to {output_dir}"
    )


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=project_root / "data" / "processed" / "cleaned_online_retail.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "outputs" / "uci_online_retail",
    )
    parser.add_argument("--min-support", type=float, default=0.02)
    parser.add_argument("--min-confidence", type=float, default=0.30)
    parser.add_argument("--overwrite", action="store_true", help="Replace existing output files.")
    args = parser.parse_args()
    run(
        args.input,
        args.output_dir,
        args.min_support,
        args.min_confidence,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()
