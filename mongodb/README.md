# Local MongoDB integration

The Python importer is deliberately restricted to an unauthenticated MongoDB
server on loopback (`localhost`, `127.0.0.1`, or `::1`). It always uses the
`RetailAnalytics` database. It refuses Atlas, remote hosts, and credentialed
URIs so this project's import command cannot accidentally write to production.

## MongoDB components

- **MongoDB Community Server** is the database server. It stores the imported
  collections and runs as a Windows service.
- **MongoDB Compass** is an optional graphical client for browsing databases,
  collections, and documents. It does not replace the server.
- **MongoDB Atlas** is MongoDB's hosted cloud service. It is an alternative for
  a separately configured non-production environment, but this local-only
  importer intentionally rejects Atlas/remote connection strings. Do not point
  this importer at a production cluster.

The project's inspected machine currently has the MongoDB Server Windows
service running and listening on `127.0.0.1:27017`. `pymongo` connects without
credentials to that local server. Compass is optional.

If MongoDB Community Server is not installed on another Windows machine,
download the Community Server MSI from
[mongodb.com/try/download/community](https://www.mongodb.com/try/download/community),
choose the current Windows x64 MSI, and install it as a Windows service. You
may select the bundled MongoDB Compass option in the installer, or install
Compass separately from
[mongodb.com/products/tools/compass](https://www.mongodb.com/products/tools/compass).
Start the `MongoDB` service in Windows Services if it is stopped. Compass
connects to `mongodb://127.0.0.1:27017`.

## Collections and idempotency

The importer reads only:

- `data/processed/cleaned_online_retail.csv`
- Apriori and FP-Growth itemset/rule CSVs in `outputs/uci_online_retail/`

It creates or upserts these collections:

- `sales_records`: cleaned line-level sales and return facts; monetary values
  are stored as BSON Decimal128.
- `transaction_summaries`: one document per invoice, including positive-sale
  product codes, line counts, units and gross/return/net totals.
- `market_basket_results`: frequent itemsets and association rules, labelled
  by algorithm and result type.

A SHA-256 fingerprint of the cleaned CSV scopes each import. Stable `_id`
values plus `ReplaceOne(..., upsert=True)` make a repeat import idempotent. The
importer batches writes (default 1,000 documents), makes indexes, removes stale
documents only for this same dataset fingerprint after all upserts succeed,
and compares expected processed counts to MongoDB counts. It does not delete
other datasets or collections.

## PowerShell commands

From the project root:

```powershell
Set-Location 'C:\Users\garik\OneDrive\Documents\Desktop\market_basket_analysis'
python -m pip install -r requirements.txt
```

Check local server availability without writing project documents:

```powershell
python -m src.mongodb_integration --check
```

Import data:

```powershell
python -m src.mongodb_integration --import-data
```

The command reports a dataset fingerprint and document counts processed and
verified in each collection. Rerunning is safe for the same source: matching
documents are replaced/upserted rather than duplicated. It can take a few
minutes for the full retail file.

Run the supplied read-only aggregations after importing:

```powershell
python -m src.mongodb_integration --run-queries
```

This prints monthly net/gross revenue and return totals, monthly invoice
counts, best-selling products by positive units sold, and the highest-lift
association rules. Only set `MONGODB_URI` if it is a local loopback URI; the
default is `mongodb://127.0.0.1:27017`. Remote and Atlas URIs are intentionally
rejected.

## Tests

Run `python -m unittest discover -s tests -v`. MongoDB integration unit tests
use an in-memory fake database; they do not write to MongoDB. The `--check`,
`--import-data`, and `--run-queries` commands are live local-server steps and
are separate from those unit tests.
