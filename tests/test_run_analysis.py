import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data_preprocessing import clean_transactions
from src.run_analysis import run


class RunAnalysisTests(unittest.TestCase):
    def test_writes_sales_market_basket_and_comparison_outputs(self) -> None:
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
            ["10001", "A1", "Tea", 1, "2010-12-01", 2.0, "101", "UK"],
            ["10001", "B2", "Coffee", 1, "2010-12-01", 3.0, "101", "UK"],
            ["10002", "A1", "Tea", 1, "2010-12-02", 2.0, None, "UK"],
            ["10002", "B2", "Coffee", 1, "2010-12-02", 3.0, None, "UK"],
            ["10003", "A1", "Tea", 1, "2010-12-03", 2.0, "103", "France"],
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "cleaned.csv"
            output = root / "results"
            raw_path = root / "raw.csv"
            pd.DataFrame(rows, columns=columns).to_csv(raw_path, index=False)
            cleaned, _ = clean_transactions(raw_path)
            cleaned.to_csv(source, index=False)

            run(source, output, min_support=0.5, min_confidence=0.5)

            self.assertTrue((output / "sales_summary.csv").is_file())
            self.assertTrue((output / "sales_by_month.csv").is_file())
            self.assertTrue((output / "sales_by_country.csv").is_file())
            self.assertTrue((output / "sales_by_product.csv").is_file())
            self.assertTrue((output / "sales_by_month.png").is_file())
            self.assertTrue((output / "top_products_by_sales.png").is_file())
            self.assertTrue((output / "algorithm_comparison.png").is_file())

            summary = pd.read_csv(output / "sales_summary.csv").iloc[0]
            self.assertEqual(summary["cleaned_invoice_lines"], 5)
            self.assertEqual(summary["distinct_invoices"], 3)
            self.assertEqual(summary["known_customers"], 2)
            self.assertEqual(summary["net_sales_amount"], 12.0)

            apriori = pd.read_csv(output / "frequent_itemsets_apriori.csv")
            fpgrowth = pd.read_csv(output / "frequent_itemsets_fpgrowth.csv")
            self.assertEqual(
                set(zip(apriori["itemset"], apriori["support_count"])),
                set(zip(fpgrowth["itemset"], fpgrowth["support_count"])),
            )
            self.assertIn("A1 | B2", set(apriori["itemset"]))

            summary_path = output / "sales_summary.csv"
            existing_summary = summary_path.read_bytes()
            with self.assertRaises(FileExistsError):
                run(source, output, min_support=0.5, min_confidence=0.5)
            self.assertEqual(summary_path.read_bytes(), existing_summary)


if __name__ == "__main__":
    unittest.main()
