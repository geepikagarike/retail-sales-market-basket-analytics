# Tableau dashboard guide

Connect Tableau to
`data/processed/cleaned_online_retail.csv`. The actual output files are under
`outputs/uci_online_retail/`. Use `InvoiceDate` as a date/time, and verify
`Quantity`, `UnitPrice`, and `SalesAmount` are numeric. Keep `InvoiceNo` and
`StockCode` as text dimensions.

Suggested views:

- **Sales Trends:** monthly sales line chart, country comparison, top products.
- **Product Associations:** ranked rules from
  `outputs/uci_online_retail/association_rules_apriori.csv` or
  `association_rules_fpgrowth.csv`, with support, confidence, and lift.
- **Business Insights:** verified findings and recommendations with method and
  limitations.

Treat association rules as co-occurrence, not proof of causation. State the
minimum support and confidence settings and filter out low-count rules before
making recommendations.

Keep date and country filters scoped to sales views unless the association
rules are recalculated for those filtered transactions. The exported rules
describe the full transaction population and cannot be correctly filtered by
date or country from the current CSV alone.
