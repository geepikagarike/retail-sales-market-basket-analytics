// Create after importing and validating the cleaned order_items collection.
db.order_items.createIndex({ InvoiceNo: 1 });
db.order_items.createIndex({ StockCode: 1 });
db.order_items.createIndex({ InvoiceDate: 1 });
db.order_items.createIndex({ Country: 1, InvoiceDate: 1 });
