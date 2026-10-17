import unittest

from src.market_basket import apriori, association_rules, fpgrowth


class MarketBasketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transactions = [
            ["tea", "coffee"],
            ["tea", "coffee"],
            ["tea", "cookies"],
            ["coffee", "cookies"],
        ]

    def test_apriori_and_fpgrowth_return_same_counts(self) -> None:
        self.assertEqual(
            apriori(self.transactions, 0.5),
            fpgrowth(self.transactions, 0.5),
        )

    def test_support_uses_invoice_count(self) -> None:
        itemsets = apriori(self.transactions, 0.5)
        self.assertEqual(itemsets[frozenset({"tea"})], 3)
        self.assertEqual(itemsets[frozenset({"tea", "coffee"})], 2)

    def test_rule_metrics_are_calculated(self) -> None:
        itemsets = apriori(self.transactions, 0.5)
        rules = association_rules(itemsets, len(self.transactions), 0.6)
        tea_to_coffee = next(
            rule
            for rule in rules
            if rule["antecedent"] == "tea" and rule["consequent"] == "coffee"
        )
        self.assertAlmostEqual(tea_to_coffee["support"], 0.5)
        self.assertAlmostEqual(tea_to_coffee["confidence"], 2 / 3)
        self.assertAlmostEqual(tea_to_coffee["lift"], 8 / 9)

    def test_invalid_support_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            apriori(self.transactions, 0)


if __name__ == "__main__":
    unittest.main()
