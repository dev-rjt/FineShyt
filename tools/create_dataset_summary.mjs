import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const report = JSON.parse(await fs.readFile("data/reports/validation_report.json", "utf8"));
const sources = JSON.parse(await fs.readFile("data/external/samples/source_metadata.json", "utf8"));
const inventoryLines = (await fs.readFile("data/file_inventory.csv", "utf8")).trim().split("\n");
const inventory = inventoryLines.slice(1).map((line) => {
  const [file, rows, columns, sizeBytes, sha256] = line.split(",");
  return [file, Number(rows), Number(columns), Number(sizeBytes), sha256];
});

const wb = Workbook.create();
const summary = wb.worksheets.add("Summary");
const validation = wb.worksheets.add("Validation");
const sourceSheet = wb.worksheets.add("Sources");
const files = wb.worksheets.add("Files");
const font = "Arial";
const dark = "#17342B";
const green = "#006A4E";
const pale = "#E8F4EF";

for (const sheet of [summary, validation, sourceSheet, files]) {
  sheet.showGridLines = false;
}

summary.getRange("A2:H2").merge();
summary.getRange("A2").values = [["Green Insights dataset summary"]];
summary.getRange("A2").format.font = { name: font, size: 16, bold: true, color: dark };
summary.getRange("A3:H3").format.borders = { bottom: { style: "thin", color: green } };
summary.getRange("A5:B5").values = [["Metric", "Value"]];
const countRows = Object.entries(report.counts).map(([key, value]) => [key.replaceAll("_", " "), value]);
summary.getRange("A6").write(countRows);
summary.getRange(`A5:B${5 + countRows.length}`).format.borders = { preset: "inside", style: "thin", color: "#D6E1DC" };
summary.getRange("A5:B5").format = { fill: green, font: { name: font, bold: true, color: "#FFFFFF" } };
summary.getRange("B6:B20").format.numberFormat = "#,##0";

summary.getRange("D5:E5").values = [["Product", "Take-up rate"]];
const rateRows = Object.entries(report.takeup_rates).map(([key, value]) => [key, value]);
summary.getRange("D6").write(rateRows);
summary.getRange(`D5:E${5 + rateRows.length}`).format.borders = { preset: "inside", style: "thin", color: "#D6E1DC" };
summary.getRange("D5:E5").format = { fill: green, font: { name: font, bold: true, color: "#FFFFFF" } };
summary.getRange("E6:E12").format.numberFormat = "0.0%";

summary.getRange("D12:E12").values = [["Validation", report.overall_status]];
summary.getRange("D12:E12").format = { fill: pale, font: { name: font, bold: true, color: dark }, borders: { preset: "outside", style: "thin", color: green } };
summary.getRange("A18:B18").values = [["Transaction category", "Rows"]];
const categoryRows = Object.entries(report.transaction_category_counts).map(([key, value]) => [key, value]);
summary.getRange("A19").write(categoryRows);
summary.getRange("A18:B18").format = { fill: green, font: { name: font, bold: true, color: "#FFFFFF" } };
summary.getRange("B19:B30").format.numberFormat = "#,##0";
summary.getRange("A:B").format.columnWidth = 27;
summary.getRange("D:D").format.columnWidth = 29;
summary.getRange("E:E").format.columnWidth = 18;
summary.getRange("A2:E26").format.font = { name: font, size: 10, color: "#263A33" };
summary.getRange("A2").format.font = { name: font, size: 16, bold: true, color: dark };

validation.getRange("A2:C2").merge();
validation.getRange("A2").values = [["Validation checks"]];
validation.getRange("A2").format.font = { name: font, size: 16, bold: true, color: dark };
validation.getRange("A4:C4").values = [["Check", "Status", "Detail"]];
validation.getRange("A5").write(report.checks.map((x) => [x.check, x.status, x.detail]));
validation.getRange("A4:C4").format = { fill: green, font: { name: font, bold: true, color: "#FFFFFF" } };
validation.getRange("A4:C40").format.borders = { preset: "inside", style: "thin", color: "#D6E1DC" };
validation.getRange("A:A").format.columnWidth = 38;
validation.getRange("B:B").format.columnWidth = 13;
validation.getRange("C:C").format.columnWidth = 60;
validation.getRange("A4:C40").format.wrapText = true;
validation.getRange("A2:C36").format.font = { name: font, size: 10, color: "#263A33" };
validation.getRange("A2").format.font = { name: font, size: 16, bold: true, color: dark };
validation.freezePanes.freezeRows(4);

sourceSheet.getRange("A2:D2").merge();
sourceSheet.getRange("A2").values = [["Public sources and usage"]];
sourceSheet.getRange("A2").format.font = { name: font, size: 16, bold: true, color: dark };
sourceSheet.getRange("A4:D4").values = [["Source", "Landing page", "Licence / publisher", "How it is used"]];
const sourceRows = [
  ["UCI Online Retail II", sources.uci_online_retail_ii.landing_page, sources.uci_online_retail_ii.license, sources.uci_online_retail_ii.usage],
  ["London smart-meter data", sources.london_smart_meter.landing_page, sources.london_smart_meter.license, sources.london_smart_meter.usage],
  ["UK GHG Conversion Factors 2026", sources.uk_ghg_conversion_factors_2026.landing_page, sources.uk_ghg_conversion_factors_2026.publisher, sources.uk_ghg_conversion_factors_2026.usage],
];
sourceSheet.getRange("A5").write(sourceRows);
sourceSheet.getRange("A4:D4").format = { fill: green, font: { name: font, bold: true, color: "#FFFFFF" } };
sourceSheet.getRange("A4:D7").format.borders = { preset: "inside", style: "thin", color: "#D6E1DC" };
sourceSheet.getRange("A4:D7").format.wrapText = true;
sourceSheet.getRange("A:A").format.columnWidth = 30;
sourceSheet.getRange("B:B").format.columnWidth = 55;
sourceSheet.getRange("C:C").format.columnWidth = 25;
sourceSheet.getRange("D:D").format.columnWidth = 70;
sourceSheet.getRange("A2:D7").format.font = { name: font, size: 10, color: "#263A33" };
sourceSheet.getRange("A2").format.font = { name: font, size: 16, bold: true, color: dark };

files.getRange("A2:E2").merge();
files.getRange("A2").values = [["Generated CSV inventory"]];
files.getRange("A2").format.font = { name: font, size: 16, bold: true, color: dark };
files.getRange("A4:E4").values = [["File", "Rows", "Columns", "Size (bytes)", "SHA-256"]];
files.getRange("A5").write(inventory);
files.getRange("A4:E4").format = { fill: green, font: { name: font, bold: true, color: "#FFFFFF" } };
files.getRange("B5:D40").format.numberFormat = "#,##0";
files.getRange("A:A").format.columnWidth = 48;
files.getRange("B:D").format.columnWidth = 16;
files.getRange("E:E").format.columnWidth = 68;
files.getRange(`A2:E${4 + inventory.length}`).format.font = { name: font, size: 10, color: "#263A33" };
files.getRange("A2").format.font = { name: font, size: 16, bold: true, color: dark };
files.freezePanes.freezeRows(4);

// Reapply headers after base font formatting.
for (const range of [summary.getRange("A5:B5"), summary.getRange("D5:E5"), summary.getRange("A18:B18"), validation.getRange("A4:C4"), sourceSheet.getRange("A4:D4"), files.getRange("A4:E4")]) {
  range.format = { fill: green, font: { name: font, bold: true, color: "#FFFFFF" } };
}

wb.recalculate();
await fs.mkdir("data/reports/previews", { recursive: true });
for (const name of ["Summary", "Validation", "Sources", "Files"]) {
  const image = await wb.render({ sheetName: name, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(`data/reports/previews/${name.toLowerCase()}.png`, new Uint8Array(await image.arrayBuffer()));
}

const check = await wb.inspect({ kind: "table", sheetId: "Summary", range: "A1:H30", include: "values,formulas", tableMaxRows: 30, tableMaxCols: 8 });
await fs.writeFile("data/reports/workbook_inspection.ndjson", check.ndjson, "utf8");
const errors = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
await fs.writeFile("data/reports/workbook_formula_errors.ndjson", errors.ndjson, "utf8");

const output = await SpreadsheetFile.exportXlsx(wb);
await output.save("data/reports/dataset_summary.xlsx");
console.log("data/reports/dataset_summary.xlsx");
