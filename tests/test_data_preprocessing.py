import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data_preprocessing import clean_transactions


class DataPreprocessingTests(unittest.TestCase):
    def test_keeps_returns_and_unknown_customers_but_excludes_invalid_rows(self) -> None:
        columns = [
            "InvoiceNo",
            "StockCode",
            "Description",
            "Quantity",
            "InvoiceDate",
            "UnitPrice",
            "CustomerID",
            "Country",
        ]
        rows = [
            ["10001", "A1", "café", 2, "12/1/10 8:26", 2.5, None, "UK"],
            ["10001", "A1", "café", 2, "12/1/10 8:26", 2.5, None, "UK"],
            ["10002", "B2", None, -1, "12/2/10 9:00", 3.0, "123", "UK"],
            ["C10003", "C3", "cancelled", -1, "12/2/10 9:00", 3.0, "123", "UK"],
            ["10004", "D4", "zero", 0, "12/2/10 9:00", 3.0, "123", "UK"],
            ["10005", "E5", "bad price", 1, "12/2/10 9:00", 0, "123", "UK"],
            ["10006", "F6", "bad date", 1, "not-a-date", 3.0, "123", "UK"],
            ["10007", "G7", "bad quantity", "bad", "12/2/10 9:00", 3.0, "123", "UK"],
            [None, "H8", "missing invoice", 1, "12/2/10 9:00", 3.0, "123", "UK"],
        ]
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "online_retail.csv"
            pd.DataFrame(rows, columns=columns).to_csv(
                input_path, index=False, encoding="cp1252"
            )
            original_bytes = input_path.read_bytes()

            cleaned, report = clean_transactions(input_path)

            self.assertEqual(input_path.read_bytes(), original_bytes)
            self.assertEqual(len(cleaned), 2)
            self.assertEqual(set(cleaned["TransactionType"]), {"Sale", "Return"})
            self.assertAlmostEqual(cleaned["SalesAmount"].sum(), 2.0)
            self.assertEqual(cleaned["CustomerID"].isna().sum(), 1)
            self.assertEqual(report["rows_retained_as_returns"], 1)
            self.assertEqual(report["rows_eligible_for_market_basket"], 1)
            self.assertEqual(report["missing_customer_ids_retained"], 1)
            self.assertEqual(report["rows_dropped_by_reason"]["cancelled_invoice"], 1)
            self.assertEqual(report["rows_dropped_by_reason"]["duplicate_row"], 1)
            self.assertEqual(report["rows_dropped_by_reason"]["zero_quantity"], 1)
            self.assertEqual(report["rows_dropped_by_reason"]["non_positive_unit_price"], 1)


if __name__ == "__main__":
    unittest.main()
