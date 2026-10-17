# Power BI Desktop: Retail Sales & Market Basket Dashboard

Beginner-friendly setup using the project's existing CSV exports. CSV is the
supported starting connection: this guide does **not** assume Power BI can
connect directly to MongoDB. No `.pbix` file is included or claimed.

## 1. Available files and recommended sources

Open the project folder:

```text
C:\Users\garik\OneDrive\Documents\Desktop\market_basket_analysis
```

| File | Contents | Power BI use |
|---|---|---|
| `data\processed\cleaned_online_retail.csv` | 524,878 cleaned invoice-line records. Fields include invoice, product code/description, quantity, date/time, unit price, optional customer ID, country, sales amount, and sale/return type. | **Main source.** One row per cleaned invoice-product line. Keep this at line grain for sales measures. |
| `outputs\uci_online_retail\sales_summary.csv` | One overall summary row: cleaned lines, invoices, products, customers, sales, returns, revenue, and units. | Validation only; don't add its totals to the line fact table. |
| `outputs\uci_online_retail\sales_by_month.csv` | One aggregate row per month, with net/gross sales, returns, units, and invoice count. | Optional pre-aggregated monthly chart. Do not relate or sum alongside line-level sales measures; it will double-count if combined incorrectly. |
| `outputs\uci_online_retail\sales_by_country.csv` | Sales, returns, and invoices summarized by country. | Optional validation/reference only; prefer country slicers on the line-level fact. |
| `outputs\uci_online_retail\sales_by_product.csv` | Sales, return, quantity, and invoice totals summarized by product code. | Optional validation/reference only; make product visuals from the line-level fact to retain filter behavior. |
| `outputs\uci_online_retail\association_rules_apriori.csv` | Apriori rules, each with antecedent, consequent, support count, support, confidence, and lift. | Recommended rules table. Disconnected from sales dimensions because the rules were mined across the whole transaction population. |
| `outputs\uci_online_retail\association_rules_fpgrowth.csv` | The corresponding FP-Growth rule export with the same fields. | Optional alternative rules table. Import this instead of Apriori for a single-algorithm view, or compare in a separately designed table. |
| `outputs\uci_online_retail\frequent_itemsets_apriori.csv` | Apriori itemsets with itemset size, support count, and support. | Optional analysis detail; not required for the dashboard requested here. |
| `outputs\uci_online_retail\frequent_itemsets_fpgrowth.csv` | FP-Growth itemsets with the same fields. | Optional analysis detail. |
| `outputs\uci_online_retail\algorithm_comparison.csv` | Transaction/itemset/rule counts and observed runtimes and thresholds by algorithm. | Optional methodology page; runtime is specific to the recorded run and machine. |

There is no need to create another Power BI data folder or copy the 52 MB
cleaned CSV. Connect Power BI to its existing path. A `.pbix` is a binary
Power BI Desktop project and cannot be truthfully generated or checked in this
environment; Power BI Desktop was not detected in the workspace machine's
standard install paths or app list.

## 2. First dashboard step: load the main CSV

On Windows:

1. Install and open **Microsoft Power BI Desktop** from the Microsoft Store or
   Microsoft's official Power BI Desktop download page.
2. Select **Home > Get data > Text/CSV**.
3. Browse to:

   ```text
   C:\Users\garik\OneDrive\Documents\Desktop\market_basket_analysis\data\processed\cleaned_online_retail.csv
   ```
4. In the preview, confirm that columns are separated correctly and the first
   row contains column names. Choose **Transform Data** (not Load) to open Power
   Query Editor.
5. Rename the query to `Sales`. Continue with the type and quality checks below,
   then select **Close & Apply**.

The CSV is about 52 MB, so initial load can take a little time. If Power BI
asks whether to replace an existing query with the same name, review the model
before confirming.

### Import the association-rule table

After the main table is loaded, use **Home > New Source > Text/CSV**, select
`outputs\uci_online_retail\association_rules_apriori.csv`, choose **Transform
Data**, and rename the query `AssociationRules`. Keep it disconnected (no
relationship to `Sales`, Date, Country, or Product).

You can use `association_rules_fpgrowth.csv` instead if you want FP-Growth
rules. Do not append both without adding an `Algorithm` column, otherwise the
two equivalent rule sets may look like duplicate findings.

## 3. Power Query: types and data quality

### `Sales` types

In Power Query Editor, select each column and choose the indicated **Data Type**
from **Transform > Data Type**:

| Column | Type |
|---|---|
| `InvoiceNo` | Text |
| `StockCode` | Text |
| `Description` | Text |
| `Quantity` | Whole Number |
| `InvoiceDate` | Date/Time |
| `UnitPrice` | Decimal Number (or Fixed Decimal Number if appropriate to your locale/model) |
| `CustomerID` | Text (identifier, not a measure) |
| `Country` | Text |
| `SalesAmount` | Decimal Number |
| `TransactionType` | Text |

The source dates are ISO formatted (`yyyy-MM-dd HH:mm:ss`), which Power Query
normally recognizes. If a conversion error appears, select `InvoiceDate` >
**Change Type > Using Locale...**, choose **Date/Time**, and use a locale that
parses year-month-day unambiguously. Check the first and last dates after
conversion.

### Add a date-only key

The source `InvoiceDate` includes hours and minutes. A Date dimension is keyed
by midnight, so relate it to a date-only column, not directly to the
timestamp. In Power Query, select **Add Column > Date > Date Only** while
`InvoiceDate` is selected. Rename the new column `InvoiceDateDate` and verify
its type is **Date**. This transformation is row-preserving.

### Check nulls, duplicates, and values

1. In Power Query, enable **View > Column quality**, **Column distribution**,
   and **Column profile**. Change profiling from the default top 1,000 rows to
   the entire data set where available.
2. Confirm `InvoiceNo`, `StockCode`, `InvoiceDate`, `Quantity`, `UnitPrice`,
   and `SalesAmount` have no errors or nulls. Resolve type-conversion errors
   explicitly; don't replace them silently with zero.
3. `CustomerID` is **expected to be blank** for some rows. Keep those rows;
   customer ID is not needed for sales, invoice, product, or basket visuals.
   The inspected file has 132,186 blank customer IDs, so a unique-customer
   card would undercount actual buyers and should be omitted or labelled
   "identified customers only."
4. Check that `InvoiceDate` falls between 2010-12-01 and 2011-12-09 and that
   Quantity/price/sales columns are numeric.
5. Use **Home > Keep Rows > Keep Duplicates** as a temporary duplicate check
   only if useful, then undo/remove that diagnostic step. Do not remove rows
   just because `InvoiceNo` repeats: an invoice normally has multiple product
   lines. The actual cleaned file has no exact duplicate rows.
6. Confirm there are 524,878 rows after transformations. Adding
   `InvoiceDateDate` should not change row count.
7. Verify the current source contains no return rows (`TransactionType` is
   `Sale` for every retained row in the inspected data). Keep the measures
   below return-aware so a future cleaned source containing returns is handled
   consistently.

### `AssociationRules` types

Set `antecedent` and `consequent` to **Text**, `support_count` to **Whole
Number**, and `support`, `confidence`, and `lift` to **Decimal Number**. Do
not change the item labels to numbers: product identifiers are labels.

## 4. Data model

Use a star-like model with one sales fact table:

```text
Date[Date]       1 ─── * Sales[InvoiceDateDate]
Country[Country] 1 ─── * Sales[Country]       (optional dimension)

AssociationRules     (disconnected; no relationship)
```

### Date dimension

In Power BI Desktop, select **Modeling > New table** and create:

```DAX
Date =
ADDCOLUMNS (
    CALENDAR ( MIN ( Sales[InvoiceDateDate] ), MAX ( Sales[InvoiceDateDate] ) ),
    "Year", YEAR ( [Date] ),
    "Month Number", MONTH ( [Date] ),
    "Month", FORMAT ( [Date], "MMM" ),
    "Year Month", FORMAT ( [Date], "yyyy-MM" ),
    "YearMonthSort", YEAR ( [Date] ) * 100 + MONTH ( [Date] )
)
```

Select `Date[Year Month]`, choose **Column tools > Sort by column >
YearMonthSort**. Select the Date table and **Table tools > Mark as date table >
Date**.

In **Model view**, create a single-direction, one-to-many relationship from
`Date[Date]` to `Sales[InvoiceDateDate]`, active. If Power BI auto-creates an
ambiguous or many-to-many relationship, delete it and set the fields and
cardinality explicitly.

### Country and Product dimensions (optional)

For country, create a **Reference** of `Sales` in Power Query, keep only
`Country`, remove duplicates, rename the query `Country`, and relate
`Country[Country]` (one) to `Sales[Country]` (many). In the inspected cleaned
file Country has no missing values and 38 distinct values.

No separate product table is necessary for this dashboard. Use the actual
`Sales[StockCode]` as the product category and show `Sales[Description]` as a
tooltip. If you later add a Product dimension, first verify that each
`StockCode` maps to exactly one description, then make its code unique on the
one-side of a one-to-many relationship.

**Do not connect `AssociationRules` to Sales or the dimensions.** Each rule's
support/confidence/lift describes the entire mined basket population; those
CSV rows do not contain dates or countries. Date/country slicers therefore
cannot legitimately change those rule metrics. A filtered rule analysis would
need to rerun mining on the selected invoice subset outside this static CSV
model.

## 5. DAX measures

Create measures by selecting the `Sales` table in the Fields pane and choosing
**Table tools > New measure**. Use the exact table and column names below.

```DAX
Total Revenue =
SUM ( Sales[SalesAmount] )

Total Orders =
DISTINCTCOUNT ( Sales[InvoiceNo] )

Total Quantity =
CALCULATE (
    SUM ( Sales[Quantity] ),
    KEEPFILTERS ( Sales[Quantity] > 0 )
)

Average Order Value =
DIVIDE ( [Total Revenue], [Total Orders], 0 )

Monthly Revenue =
[Total Revenue]

Product Revenue =
CALCULATE (
    [Total Revenue],
    KEEPFILTERS ( Sales[Quantity] > 0 )
)

Product Units Sold =
[Total Quantity]
```

`Total Revenue` is net `SalesAmount`; returns, if present, subtract from it.
`Total Quantity` and product ranking use positive quantities only.
`Monthly Revenue` is deliberately the same revenue measure evaluated under the
Date relationship/filter context; no separate monthly aggregation is needed.
For the inspected current cleaned file there are no returns, so gross and net
revenue are equal.

Do **not** add a unique-customer KPI by default. Customer IDs are missing for
132,186 of 524,878 lines; the `CustomerID` column is available but incomplete.
If you choose to show a qualified count, use:

```DAX
Identified Customers =
CALCULATE (
    DISTINCTCOUNT ( Sales[CustomerID] ),
    KEEPFILTERS ( Sales[CustomerID] <> BLANK () )
)
```

Label it **Identified customers (CustomerID present)**, not total customers.
Power BI's `DISTINCTCOUNT` excludes blank values, but missing IDs can represent
multiple unknown people.

## 6. Build the report visuals

Create a new report page. Format revenue measures as currency from **Measure
tools > Format** and choose the correct currency/locale. This dataset's
`UnitPrice` is in sterling; confirm the intended currency symbol before
publishing.

### KPI cards

For each KPI, add a **Card** visual and drag one measure into **Data/Fields**:

- Card 1: `[Total Revenue]`
- Card 2: `[Total Orders]`
- Card 3: `[Total Quantity]`
- Card 4: `[Average Order Value]`

Set meaningful titles, display units to None (or a clear thousands/millions
unit), and decimal places appropriate to the value. The currently validated
baseline, with no filters, is revenue `10,642,110.804`, orders `19,960`, and
positive units `5,572,420`. AOV is revenue divided by orders.

### Monthly revenue trend

Add a **Line chart**:

- X-axis: `Date[Year Month]`
- Y-axis: `[Monthly Revenue]`
- Sort the axis chronologically by `YearMonthSort` (not alphabetically by
  month name).
- Format the Y-axis as currency, turn on markers if desired, and title it
  "Monthly Net Revenue".

### Top 10 products by revenue

Add a **Clustered bar chart**:

- Y-axis: `Sales[StockCode]`
- X-axis: `[Product Revenue]`
- Tooltips: `Sales[Description]`, `[Product Units Sold]`.
- In the Filters pane, add the product description/code to **Filters on this
  visual**, change filter type to **Top N**, enter `10`, set **By value** to
  `[Product Revenue]`, then click **Apply filter**.
- Sort descending by `[Product Revenue]`; format X-axis as currency.

### Best-selling products by quantity

Add another **Clustered bar chart**:

- Y-axis: `Sales[StockCode]`
- X-axis: `[Product Units Sold]`
- Tooltips: `Sales[Description]`, `[Product Revenue]`.
- Apply a **Top N = 10** visual filter **By value** `[Product Units Sold]`.
- Sort descending by units; set the X-axis title to "Units sold".

### Association rules table

Add a **Table** visual and drag these columns from `AssociationRules`:

- `antecedent`
- `consequent`
- `support_count`
- `support`
- `confidence`
- `lift`

Format `support` and `confidence` as percentages (two decimal places), and
`lift` as a decimal (two places). Sort by `lift` descending or
`support_count` descending, and optionally use a visual-level filter on
`support_count` so a very low-volume rule is not overemphasized. Title the
visual "Apriori product association rules (whole dataset)". These are
co-occurrence statistics, not evidence of causation. If using the FP-Growth
file, name the table accordingly.

### Slicers

Add **Slicer** visuals:

- Date slicer: `Date[Date]` (Between or Relative date). It filters Sales visuals
  through the Date relationship.
- Country slicer: `Country[Country]` if the Country dimension was created;
  otherwise use `Sales[Country]`. It filters Sales visuals.

With **Format > Edit interactions**, check the slicers filter sales KPI cards,
monthly trend, and product charts as intended. Because `AssociationRules` is
disconnected, date and country slicers should **not** filter its table. Keep
that scope visible in the table title or add a note.

## 7. Validation against the current Python and MongoDB outputs

The inspected current cleaned CSV has 524,878 rows, 19,960 distinct invoice
numbers, 3,922 products, 5,572,420 positive units, date range
2010-12-01 through 2011-12-09, 38 countries, 132,186 blank CustomerIDs, and
no exact duplicate rows. It has no return rows.

The Python `sales_summary.csv` reports:

| Check | Expected |
|---|---:|
| `cleaned_invoice_lines` | 524,878 |
| `distinct_invoices` | 19,960 |
| `distinct_products` | 3,922 |
| `units_sold` | 5,572,420 |
| `gross_sales_amount` | 10,642,110.804 |
| `net_sales_amount` | 10,642,110.804 |
| `return_lines` | 0 |

The Python monthly export sums to net sales `10,642,110.804`. The local
MongoDB `transaction_summaries` monthly-revenue aggregation was run for the
same cleaned-file fingerprint and also sums to `10,642,110.804` across 13
months. MongoDB count verification for that data set was 524,878 sales
documents and 19,960 invoice summaries.

To validate in Power BI with no slicers/filters active:

1. Compare the three KPI cards to the expected revenue, order, and unit totals
   above. Allow for display rounding; compare the underlying decimal value.
2. Create a temporary card with `COUNTROWS(Sales)`; it should be 524,878.
3. Create a temporary card with
   `DISTINCTCOUNT(Sales[StockCode])`; it should be 3,922.
4. Put `Date[Year Month]` and `[Monthly Revenue]` in a temporary table. Export
   if needed, then compare each month to `sales_by_month.csv`'s
   `Month`/`net_sales_amount`. The monthly total must sum to 10,642,110.804.
5. Confirm the monthly-revenue grand total equals the Total Revenue card, and
   verify the model has no accidental many-to-many relationship or duplicate
   aggregate table contributing to the measures.
6. Check the MongoDB verification values in `mongodb/README.md` / the import
   command report. Dashboard and MongoDB baselines should agree with the
   Python export.

For more exact numeric validation, Power BI's visual display may round.
Compare exported detail or the underlying measure with adequate decimal
precision. Do not add the overall summary or monthly/country/product aggregate
CSV totals into the same line-level model as additive fact records.

## 8. Power BI and MongoDB connection note

CSV via **Get Data > Text/CSV** is the reliable initial connection used here.
Power BI Desktop's MongoDB connector availability depends on the current
Power BI release, connector support, and often an ODBC driver/provider. Do not
assume a direct connector is built in. If later using a supported connector,
install and validate its documented driver and credentials separately, test
against local/non-production MongoDB, and reconcile to the same Python totals.
Do not put database credentials in this README or in a PBIX.
