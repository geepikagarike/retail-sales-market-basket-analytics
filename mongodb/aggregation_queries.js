// Run in mongosh against the RetailAnalytics database.
// Documents in order_items use the cleaned invoice-line CSV field names.

// Top products by quantity and sales.
db.order_items.aggregate([
  {
    $group: {
      _id: "$StockCode",
      description: { $first: "$Description" },
      totalQuantity: { $sum: "$Quantity" },
      totalSales: { $sum: "$SalesAmount" }
    }
  },
  { $sort: { totalSales: -1 } },
  { $limit: 10 }
]);

// Monthly sales trend.
db.order_items.aggregate([
  {
    $group: {
      _id: {
        year: { $year: "$InvoiceDate" },
        month: { $month: "$InvoiceDate" }
      },
      totalSales: { $sum: "$SalesAmount" },
      invoices: { $addToSet: "$InvoiceNo" }
    }
  },
  {
    $project: {
      totalSales: 1,
      orderCount: { $size: "$invoices" }
    }
  },
  { $sort: { "_id.year": 1, "_id.month": 1 } }
]);

// Sales by country. Customer identifiers are optional for this analysis.
db.order_items.aggregate([
  { $match: { Country: { $type: "string", $ne: "" } } },
  {
    $group: {
      _id: "$Country",
      totalSales: { $sum: "$SalesAmount" },
      invoices: { $addToSet: "$InvoiceNo" }
    }
  },
  { $project: { totalSales: 1, orderCount: { $size: "$invoices" } } },
  { $sort: { totalSales: -1 } }
]);
