# Power BI deliverable guide

Load `data/processed/cleaned_online_retail.csv` and set `InvoiceDate` to Date/Time,
`Quantity` and `UnitPrice` to Decimal Number, and `SalesAmount` to Decimal
Number. This CSV workflow is the portable default; a direct MongoDB connection
may require a supported connector or ODBC driver.

Suggested measures (adjust the table name if it differs):

```DAX
Total Sales = SUM(OrderItems[SalesAmount])

Total Units Sold = SUM(OrderItems[Quantity])

Total Orders = DISTINCTCOUNT(OrderItems[InvoiceNo])

Average Order Value = DIVIDE([Total Sales], [Total Orders], 0)

Unique Customers = DISTINCTCOUNT(OrderItems[CustomerID])
```

`Unique Customers` is meaningful only when customer IDs are present and
consistent. Create a Date table and relate it to `OrderItems[InvoiceDate]` for
time-intelligence measures. Suggested report pages: Executive Sales Overview,
Product Performance, and Market Basket Insights. Reconcile displayed sales
against the cleaned CSV before publishing.
