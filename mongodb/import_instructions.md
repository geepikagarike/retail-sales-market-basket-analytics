# MongoDB setup

1. Create a database named `RetailAnalytics`.
2. Run the Python pipeline and use `outputs/cleaned_transactions.csv`.
3. Import that CSV into a collection named `order_items` with MongoDB Compass or `mongoimport`. Parse `InvoiceDate` as a BSON Date and `Quantity`, `UnitPrice`, and `SalesAmount` as numeric values; CSV importers may otherwise infer strings.
4. Confirm document count against the CSV row count and inspect representative documents before running the examples in `aggregation_queries.js` and `indexes.js`.

Keep product and customer lookup collections optional. For this dataset, line-level order records already include product descriptions and country. Do not build customer-level analysis when IDs are absent or unreliable. Only add `$lookup` stages after confirming join keys and uniqueness.
