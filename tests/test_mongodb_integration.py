import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import mongodb_integration as integration


class FakeReplaceOne:
    def __init__(self, selector, replacement, upsert):
        self.selector = selector
        self.replacement = replacement
        self.upsert = upsert


class FakeCollection:
    def __init__(self):
        self.documents = {}
        self.bulk_calls = 0

    def bulk_write(self, operations, ordered):
        self.bulk_calls += 1
        for operation in operations:
            self.documents[operation.selector["_id"]] = operation.replacement

    def find(self, query):
        identifiers = set(query["_id"]["$in"])
        return [
            document
            for document_id, document in self.documents.items()
            if document_id in identifiers
        ]

    def count_documents(self, query):
        return sum(
            document.get("dataset_id") == query["dataset_id"]
            for document in self.documents.values()
        )

    def delete_many(self, query):
        dataset_id = query["dataset_id"]
        excluded_run = query["import_run_id"]["$ne"]
        stale_ids = [
            document_id
            for document_id, document in self.documents.items()
            if document.get("dataset_id") == dataset_id
            and document.get("import_run_id") != excluded_run
        ]
        for document_id in stale_ids:
            del self.documents[document_id]
        return len(stale_ids)

    def create_index(self, *args, **kwargs):
        return None


class FakeDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, FakeCollection())


class MongoIntegrationTests(unittest.TestCase):
    def test_local_uri_defaults_to_loopback_and_rejects_remote_uri(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(integration.local_mongodb_uri(), "mongodb://127.0.0.1:27017")
        with patch.dict(os.environ, {"MONGODB_URI": "mongodb+srv://host.example/db"}):
            with self.assertRaises(ValueError):
                integration.local_mongodb_uri()

    def test_imports_dataset_idempotently_and_verifies_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cleaned = root / "cleaned.csv"
            with cleaned.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=[
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
                    ],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "InvoiceNo": "10001",
                            "StockCode": "A1",
                            "Description": "Tea",
                            "Quantity": "2",
                            "InvoiceDate": "2010-12-01 08:26:00",
                            "UnitPrice": "2.50",
                            "CustomerID": "",
                            "Country": "UK",
                            "SalesAmount": "5.00",
                            "TransactionType": "Sale",
                        },
                        {
                            "InvoiceNo": "10001",
                            "StockCode": "B2",
                            "Description": "Coffee",
                            "Quantity": "1",
                            "InvoiceDate": "2010-12-01 08:26:00",
                            "UnitPrice": "3.00",
                            "CustomerID": "",
                            "Country": "UK",
                            "SalesAmount": "3.00",
                            "TransactionType": "Sale",
                        },
                        {
                            "InvoiceNo": "10002",
                            "StockCode": "A1",
                            "Description": "Tea",
                            "Quantity": "-1",
                            "InvoiceDate": "2010-12-02 09:00:00",
                            "UnitPrice": "2.50",
                            "CustomerID": "42",
                            "Country": "UK",
                            "SalesAmount": "-2.50",
                            "TransactionType": "Return",
                        },
                    ]
                )

            results = root / "results"
            results.mkdir()
            rows = {
                "frequent_itemsets_apriori.csv": (
                    ["itemset", "itemset_size", "support_count", "support"],
                    [["A1 | B2", "2", "1", "0.5"]],
                ),
                "frequent_itemsets_fpgrowth.csv": (
                    ["itemset", "itemset_size", "support_count", "support"],
                    [["A1 | B2", "2", "1", "0.5"]],
                ),
                "association_rules_apriori.csv": (
                    ["antecedent", "consequent", "support_count", "support", "confidence", "lift"],
                    [["A1", "B2", "1", "0.5", "1.0", "1.0"]],
                ),
                "association_rules_fpgrowth.csv": (
                    ["antecedent", "consequent", "support_count", "support", "confidence", "lift"],
                    [["A1", "B2", "1", "0.5", "1.0", "1.0"]],
                ),
            }
            for filename, (headers, data) in rows.items():
                with (results / filename).open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(headers)
                    writer.writerows(data)

            database = FakeDatabase()
            with patch.object(integration, "ReplaceOne", FakeReplaceOne):
                first = integration.import_project_data(database, cleaned, results, batch_size=2)
                calls_after_first_import = {
                    name: database[name].bulk_calls for name in integration.COLLECTION_NAMES
                }
                sales_collection = database["sales_records"]
                first_document = next(iter(sales_collection.documents.values()))
                first_document["import_run_id"] = "legacy-marker"
                second = integration.import_project_data(database, cleaned, results, batch_size=2)

            self.assertEqual(first["processed_documents"], first["verified_documents"])
            self.assertEqual(second["processed_documents"], second["verified_documents"])
            self.assertEqual(
                first["verified_documents"],
                {
                    "sales_records": 3,
                    "transaction_summaries": 2,
                    "market_basket_results": 4,
                },
            )
            self.assertEqual(
                database["transaction_summaries"].count_documents(
                    {"dataset_id": first["dataset_id"]}
                ),
                2,
            )
            self.assertEqual(
                calls_after_first_import,
                {name: database[name].bulk_calls for name in integration.COLLECTION_NAMES},
            )
            transaction = next(
                document
                for document in database["transaction_summaries"].documents.values()
                if document["InvoiceNo"] == "10001"
            )
            self.assertEqual(transaction["items"], ["A1", "B2"])
            self.assertEqual(transaction["item_count"], 2)
            self.assertEqual(transaction["line_count"], 2)
            self.assertEqual(
                transaction["net_sales_amount"].to_decimal(),
                integration.Decimal("8.00"),
            )

    def test_queries_are_dataset_scoped_and_rules_use_results_collection(self) -> None:
        pipelines = integration.query_pipelines("test-dataset")
        self.assertEqual(
            pipelines["monthly_revenue"][0],
            {"$match": {"dataset_id": "test-dataset"}},
        )
        self.assertEqual(
            pipelines["top_association_rules"][0]["$match"]["result_type"],
            "association_rule",
        )
        self.assertIn("$group", pipelines["best_selling_products"][2])


if __name__ == "__main__":
    unittest.main()
