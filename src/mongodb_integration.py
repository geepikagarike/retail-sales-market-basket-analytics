"""Import project outputs into a local MongoDB database without credentials."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import urlparse

from bson.decimal128 import Decimal128
from pymongo import MongoClient, ReplaceOne
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError

DATABASE_NAME = "RetailAnalytics"
DEFAULT_LOCAL_URI = "mongodb://127.0.0.1:27017"
COLLECTION_NAMES = ("sales_records", "transaction_summaries", "market_basket_results")
ANALYSIS_FILES = (
    "frequent_itemsets_apriori.csv",
    "frequent_itemsets_fpgrowth.csv",
    "association_rules_apriori.csv",
    "association_rules_fpgrowth.csv",
)


def local_mongodb_uri() -> str:
    """Return only a loopback URI; remote/Atlas targets are intentionally refused."""
    uri = os.environ.get("MONGODB_URI", DEFAULT_LOCAL_URI).strip()
    parsed = urlparse(uri)
    if (
        parsed.scheme != "mongodb"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(
            "This importer is restricted to unauthenticated local MongoDB. "
            "Unset MONGODB_URI or set it to mongodb://127.0.0.1:27017."
        )
    return uri


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_decimal(value: str, field: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal value in {field}: {value!r}") from exc


def _money(value: str | Decimal) -> Decimal128:
    return Decimal128(str(value))


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_date(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid InvoiceDate in cleaned CSV: {value!r}") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _record_id(dataset_id: str, key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"{dataset_id}:{digest}"


def _sale_documents(
    cleaned_csv: Path, dataset_id: str
) -> tuple[Iterator[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Yield line documents while accumulating one summary per invoice."""
    transactions: dict[str, dict[str, Any]] = {}

    def records() -> Iterator[dict[str, Any]]:
        with cleaned_csv.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {
                "InvoiceNo",
                "StockCode",
                "Description",
                "Quantity",
                "InvoiceDate",
                "UnitPrice",
                "CustomerID",
                "Country",
                "SalesAmount",
                "TransactionType",
            }
            missing = required.difference(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"Cleaned CSV is missing required fields: {', '.join(sorted(missing))}"
                )

            for row_number, row in enumerate(reader, start=2):
                invoice = _optional_text(row["InvoiceNo"])
                stock_code = _optional_text(row["StockCode"])
                if not invoice or not stock_code:
                    raise ValueError(
                        f"Cleaned CSV unexpectedly has a missing invoice/product at row {row_number}."
                    )
                try:
                    quantity_decimal = _parse_decimal(row["Quantity"], "Quantity")
                    quantity = int(quantity_decimal)
                    if quantity_decimal != quantity_decimal.to_integral_value():
                        raise ValueError(f"Quantity is not an integer at row {row_number}.")
                    unit_price = _parse_decimal(row["UnitPrice"], "UnitPrice")
                    exported_sales_amount = _parse_decimal(row["SalesAmount"], "SalesAmount")
                except (InvalidOperation, ValueError) as exc:
                    raise ValueError(f"Invalid numeric value at cleaned CSV row {row_number}: {exc}") from exc
                sales_amount = quantity_decimal * unit_price
                if abs(exported_sales_amount - sales_amount) > Decimal("0.01"):
                    raise ValueError(
                        f"SalesAmount does not reconcile to Quantity * UnitPrice "
                        f"at cleaned CSV row {row_number}."
                    )
                date = _parse_date(row["InvoiceDate"])
                customer_id = _optional_text(row["CustomerID"])
                country = _optional_text(row["Country"])
                description = _optional_text(row["Description"])

                key = json.dumps(
                    [
                        invoice,
                        stock_code,
                        description,
                        quantity,
                        date.isoformat(),
                        str(unit_price),
                        customer_id,
                        country,
                    ],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                yield {
                    "_id": _record_id(dataset_id, key),
                    "dataset_id": dataset_id,
                    "InvoiceNo": invoice,
                    "StockCode": stock_code,
                    "Description": description,
                    "Quantity": quantity,
                    "InvoiceDate": date,
                    "UnitPrice": _money(unit_price),
                    "CustomerID": customer_id,
                    "Country": country,
                    "SalesAmount": _money(sales_amount),
                    "TransactionType": row["TransactionType"],
                }

                summary = transactions.get(invoice)
                if summary is None:
                    summary = {
                        "_id": _record_id(dataset_id, f"invoice:{invoice}"),
                        "dataset_id": dataset_id,
                        "InvoiceNo": invoice,
                        "InvoiceDate": date,
                        "CustomerID": customer_id,
                        "Country": country,
                        "line_count": 0,
                        "sale_line_count": 0,
                        "return_line_count": 0,
                        "gross_sales_amount": Decimal("0"),
                        "returned_amount": Decimal("0"),
                        "net_sales_amount": Decimal("0"),
                        "units_sold": 0,
                        "units_returned": 0,
                        "items": set(),
                    }
                    transactions[invoice] = summary
                summary["line_count"] += 1
                summary["InvoiceDate"] = min(summary["InvoiceDate"], date)
                if summary["CustomerID"] is None:
                    summary["CustomerID"] = customer_id
                if summary["Country"] is None:
                    summary["Country"] = country
                summary["net_sales_amount"] += sales_amount
                if quantity > 0:
                    summary["sale_line_count"] += 1
                    summary["gross_sales_amount"] += sales_amount
                    summary["units_sold"] += quantity
                    summary["items"].add(stock_code)
                elif quantity < 0:
                    summary["return_line_count"] += 1
                    summary["returned_amount"] += -sales_amount
                    summary["units_returned"] += -quantity

    return records(), transactions


def _finalized_transaction_documents(
    transactions: dict[str, dict[str, Any]], dataset_id: str
) -> Iterator[dict[str, Any]]:
    for transaction in transactions.values():
        document = dict(transaction)
        document["dataset_id"] = dataset_id
        document["items"] = sorted(document["items"])
        document["item_count"] = len(document["items"])
        for field in ("gross_sales_amount", "returned_amount", "net_sales_amount"):
            document[field] = _money(document[field])
        yield document


def _read_result_documents(path: Path, dataset_id: str) -> Iterator[dict[str, Any]]:
    is_rules = path.name.startswith("association_rules_")
    algorithm = "apriori" if "apriori" in path.name else "fpgrowth"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = (
            {"antecedent", "consequent", "support_count", "support", "confidence", "lift"}
            if is_rules
            else {"itemset", "itemset_size", "support_count", "support"}
        )
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path.name} is missing fields: {', '.join(sorted(missing))}")

        for row in reader:
            if is_rules:
                result: dict[str, Any] = {
                    "result_type": "association_rule",
                    "antecedent": [value.strip() for value in row["antecedent"].split(" | ")],
                    "consequent": [value.strip() for value in row["consequent"].split(" | ")],
                    "support_count": int(row["support_count"]),
                    "support": float(row["support"]),
                    "confidence": float(row["confidence"]),
                    "lift": float(row["lift"]),
                }
                natural_key = json.dumps(
                    [algorithm, "rule", result["antecedent"], result["consequent"]],
                    separators=(",", ":"),
                )
            else:
                result = {
                    "result_type": "frequent_itemset",
                    "items": [value.strip() for value in row["itemset"].split(" | ")],
                    "itemset_size": int(row["itemset_size"]),
                    "support_count": int(row["support_count"]),
                    "support": float(row["support"]),
                }
                natural_key = json.dumps(
                    [algorithm, "itemset", result["items"]],
                    separators=(",", ":"),
                )
            result["_id"] = _record_id(dataset_id, natural_key)
            result["dataset_id"] = dataset_id
            result["algorithm"] = algorithm
            yield result


def _batches(documents: Iterable[dict[str, Any]], batch_size: int) -> Iterator[list[dict[str, Any]]]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1.")
    batch: list[dict[str, Any]] = []
    for document in documents:
        batch.append(document)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _upsert_documents(
    collection: Collection[Any],
    documents: Iterable[dict[str, Any]],
    batch_size: int,
) -> int:
    processed = 0
    for batch in _batches(documents, batch_size):
        existing_documents = collection.find(
            {"_id": {"$in": [document["_id"] for document in batch]}}
        )
        existing_by_id = {document["_id"]: document for document in existing_documents}
        operations = []
        for document in batch:
            existing = existing_by_id.get(document["_id"])
            if existing is not None:
                # Ignore import markers written by older versions of this importer.
                comparable = {
                    key: value for key, value in existing.items() if key != "import_run_id"
                }
                if comparable == document:
                    continue
            operations.append(ReplaceOne({"_id": document["_id"]}, document, upsert=True))
        if operations:
            collection.bulk_write(operations, ordered=False)
        processed += len(batch)
    return processed


def _read_analysis_files(results_dir: Path) -> list[Path]:
    paths = [results_dir / filename for filename in ANALYSIS_FILES]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"Required analysis CSV(s) not found: {', '.join(map(str, missing))}. "
            "Run src.run_analysis first."
        )
    return paths


def import_project_data(
    database: Database[Any],
    cleaned_csv: Path,
    results_dir: Path,
    batch_size: int = 1000,
) -> dict[str, Any]:
    """Idempotently upsert cleaned sales, invoice summaries, and mining outputs."""
    if not cleaned_csv.is_file():
        raise FileNotFoundError(f"Cleaned sales CSV not found: {cleaned_csv}")
    analysis_paths = _read_analysis_files(results_dir)
    dataset_id = _file_sha256(cleaned_csv)
    sales_collection = database["sales_records"]
    transactions_collection = database["transaction_summaries"]
    results_collection = database["market_basket_results"]

    records, transactions = _sale_documents(cleaned_csv, dataset_id)
    sales_written = _upsert_documents(sales_collection, records, batch_size)
    transaction_documents = _finalized_transaction_documents(transactions, dataset_id)
    transactions_written = _upsert_documents(
        transactions_collection, transaction_documents, batch_size
    )

    result_count = 0
    for path in analysis_paths:
        result_count += _upsert_documents(
            results_collection,
            _read_result_documents(path, dataset_id),
            batch_size,
        )

    expected = {
        "sales_records": sales_written,
        "transaction_summaries": transactions_written,
        "market_basket_results": result_count,
    }
    verified: dict[str, int] = {}
    for collection_name, expected_count in expected.items():
        actual_count = database[collection_name].count_documents({"dataset_id": dataset_id})
        verified[collection_name] = actual_count
        if actual_count != expected_count:
            raise RuntimeError(
                f"Count verification failed for {collection_name}: "
                f"expected {expected_count}, found {actual_count} for dataset {dataset_id}."
            )
    return {
        "database": DATABASE_NAME,
        "dataset_id": dataset_id,
        "processed_documents": expected,
        "verified_documents": verified,
    }


def create_indexes(database: Database[Any]) -> None:
    database["sales_records"].create_index(
        [("dataset_id", 1), ("InvoiceNo", 1), ("StockCode", 1)],
        name="dataset_invoice_product",
    )
    database["sales_records"].create_index(
        [("dataset_id", 1), ("InvoiceDate", 1)],
        name="dataset_invoice_date",
    )
    database["sales_records"].create_index(
        [("dataset_id", 1), ("StockCode", 1)],
        name="dataset_product",
    )
    database["transaction_summaries"].create_index(
        [("dataset_id", 1), ("InvoiceDate", 1)],
        name="dataset_transaction_date",
    )
    database["market_basket_results"].create_index(
        [("dataset_id", 1), ("result_type", 1), ("algorithm", 1)],
        name="dataset_result_type_algorithm",
    )
    database["market_basket_results"].create_index(
        [("dataset_id", 1), ("lift", -1)],
        name="dataset_rule_lift",
    )


def query_pipelines(dataset_id: str) -> dict[str, list[dict[str, Any]]]:
    """Return read-only MongoDB aggregation pipelines for common questions."""
    match_dataset = {"$match": {"dataset_id": dataset_id}}
    return {
        "monthly_revenue": [
            match_dataset,
            {
                "$group": {
                    "_id": {
                        "year": {"$year": "$InvoiceDate"},
                        "month": {"$month": "$InvoiceDate"},
                    },
                    "net_revenue": {"$sum": "$net_sales_amount"},
                    "gross_sales": {"$sum": "$gross_sales_amount"},
                    "returns": {"$sum": "$returned_amount"},
                    "invoice_count": {"$sum": 1},
                }
            },
            {"$sort": {"_id.year": 1, "_id.month": 1}},
        ],
        "best_selling_products": [
            match_dataset,
            {"$match": {"Quantity": {"$gt": 0}}},
            {
                "$group": {
                    "_id": "$StockCode",
                    "description": {"$first": "$Description"},
                    "units_sold": {"$sum": "$Quantity"},
                    "gross_sales": {"$sum": "$SalesAmount"},
                    "invoices": {"$addToSet": "$InvoiceNo"},
                }
            },
            {
                "$project": {
                    "description": 1,
                    "units_sold": 1,
                    "gross_sales": 1,
                    "invoice_count": {"$size": "$invoices"},
                }
            },
            {"$sort": {"units_sold": -1, "_id": 1}},
            {"$limit": 20},
        ],
        "invoice_counts_by_month": [
            match_dataset,
            {
                "$group": {
                    "_id": {
                        "year": {"$year": "$InvoiceDate"},
                        "month": {"$month": "$InvoiceDate"},
                    },
                    "invoice_count": {"$sum": 1},
                }
            },
            {"$sort": {"_id.year": 1, "_id.month": 1}},
        ],
        "top_association_rules": [
            {
                "$match": {
                    "dataset_id": dataset_id,
                    "result_type": "association_rule",
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "algorithm": 1,
                    "antecedent": 1,
                    "consequent": 1,
                    "support_count": 1,
                    "support": 1,
                    "confidence": 1,
                    "lift": 1,
                }
            },
            {"$sort": {"lift": -1, "support_count": -1}},
            {"$limit": 20},
        ],
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal128):
        return str(value.to_decimal())
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    raise TypeError(f"Cannot serialize {type(value).__name__} to JSON.")


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cleaned-csv",
        type=Path,
        default=project_root / "data" / "processed" / "cleaned_online_retail.csv",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=project_root / "outputs" / "uci_online_retail",
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--check", action="store_true", help="Only ping local MongoDB.")
    parser.add_argument("--import-data", action="store_true", help="Upsert project CSV data.")
    parser.add_argument("--run-queries", action="store_true", help="Print example read-only queries.")
    args = parser.parse_args()
    if sum((args.check, args.import_data, args.run_queries)) != 1:
        parser.error("Choose exactly one of --check, --import-data, or --run-queries.")
    try:
        uri = local_mongodb_uri()
    except ValueError as exc:
        parser.error(str(exc))

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
        database = client[DATABASE_NAME]
        if args.check:
            print(f"Connected to local MongoDB; database target: {DATABASE_NAME} (ping succeeded).")
            return
        if args.import_data:
            report = import_project_data(
                database,
                args.cleaned_csv,
                args.results_dir,
                batch_size=args.batch_size,
            )
            create_indexes(database)
            print(json.dumps(report, indent=2))
            return

        dataset_id = _file_sha256(args.cleaned_csv)
        pipelines = query_pipelines(dataset_id)
        for name, pipeline in pipelines.items():
            collection_name = {
                "best_selling_products": "sales_records",
                "top_association_rules": "market_basket_results",
            }.get(name, "transaction_summaries")
            documents = list(database[collection_name].aggregate(pipeline))
            print(f"\n{name}:")
            print(json.dumps(documents, indent=2, default=_json_default))
    except PyMongoError as exc:
        print(
            f"MongoDB operation failed ({type(exc).__name__}). "
            "Confirm the local MongoDB Server service is running.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    finally:
        client.close()


if __name__ == "__main__":
    main()
