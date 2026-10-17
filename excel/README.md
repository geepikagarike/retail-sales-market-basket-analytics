# Excel cleaning workflow

Use these working files when performing the documented manual review:

- `raw_retail_data.xlsx` — preserved source copy; do not edit.
- `cleaned_retail_data.xlsx` — reviewed working data and notes.
- `data_cleaning_log.xlsx` — issue, detection, action, and evidence for each
  material cleaning decision.

The runnable Python pipeline in `src/data_preprocessing.py` applies its
documented cleaning rules and writes a quality report. Review those rules
against the source before treating its output as the final cleaned file.

Suggested Excel steps:

1. Record source, row count, date range, and distinct invoice/product counts.
2. Inspect blanks and duplicates; remove duplicates only when confirmed
   accidental.
3. Review cancellations, returns, zero/negative quantities, and invalid prices.
   Do not silently reinterpret returns as ordinary sales.
4. Standardize whitespace and validate date, quantity, and price types.
5. Calculate `SalesAmount` as `Quantity * UnitPrice` only after confirming the
   treatment of returns/cancellations.
6. Compare before/after counts and reconcile the retained total to the Python
   output.

If quantity is in `E2` and unit price in `F2`, the line sales formula is:

```excel
=E2*F2
```

Never store identifiable or restricted raw data in the public repository.
