"""
Step 3: Build the Excel weekly KPI workbook (excel/Recharge_Weekly_KPI.xlsx).

Two sheets only:
  Data       - weekly recharge rows by bank and city (paste new weeks under the existing rows)
  Dashboard  - formula-driven weekly KPIs with Bank and City filters, WoW change and an alert flag

All formulas are standard (SUMIFS, IF, IFERROR, MAX, MIN) so the file also works in Zoho Sheet
and Google Sheets, and updates automatically when new rows are pasted into Data.
Run from the project root:  python scripts/03_build_excel.py
"""
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[1]
df = pd.read_csv(ROOT / "excel" / "weekly_recharges_by_bank_city.csv", parse_dates=["week_start"])
df = df[df.week_start < "2026-10-26"]            # drop the last, partial week (26-31 Oct)
df = df.sort_values(["week_start", "bank", "city"])

NAVY, BLUE_FILL, GREY_FILL = "0B3D6E", "E7F1FB", "F4F7FB"
hdr_font, hdr_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=NAVY)
thin = Border(bottom=Side(style="thin", color="D5DDE8"))
wb = Workbook()

# ------------------------------------------------------------------ Data sheet
ws = wb.active
ws.title = "Data"
cols = ["Week start (Mon)", "Bank", "City", "Attempts", "Failed", "Success amount (₹)"]
ws.append(cols)
for r in df.itertuples(index=False):
    ws.append([r.week_start.to_pydatetime(), r.bank, r.city, int(r.attempts), int(r.failed), float(r.success_amount)])
for c in ws[1]:
    c.font, c.fill, c.alignment = hdr_font, hdr_fill, Alignment(horizontal="center", wrap_text=True)
for row in ws.iter_rows(min_row=2):
    row[0].number_format = "dd-mmm-yyyy"
    row[3].number_format = row[4].number_format = "#,##0"
    row[5].number_format = "#,##0"
for col, w in zip("ABCDEF", [16, 10, 12, 11, 10, 18]):
    ws.column_dimensions[col].width = w
ws.freeze_panes = "A2"

# ------------------------------------------------------------------ Dashboard sheet
d = wb.create_sheet("Dashboard")
d["A1"] = "FASTag Recharge — Weekly KPI Dashboard (simulated data)"
d["A1"].font = Font(bold=True, size=14, color=NAVY)
d["A2"] = "Pick a Bank and City (or All). Paste new weeks into the Data sheet and everything below updates."
d["A2"].font = Font(italic=True, color="5A6B7D")

d["A4"], d["A5"] = "Bank", "City"
d["B4"], d["B5"] = "All", "All"
for c in ("A4", "A5"):
    d[c].font = Font(bold=True)
for c in ("B4", "B5"):
    d[c].fill = PatternFill("solid", fgColor="FFF4CC")
    d[c].font = Font(bold=True)
banks = sorted(df.bank.unique()); cities = sorted(df.city.unique())
dv_b = DataValidation(type="list", formula1='"' + ",".join(["All"] + banks) + '"', allow_blank=False)
dv_c = DataValidation(type="list", formula1='"' + ",".join(["All"] + cities) + '"', allow_blank=False)
d.add_data_validation(dv_b); d.add_data_validation(dv_c); dv_b.add("B4"); dv_c.add("B5")
# helper criteria (hidden-looking, small grey): "*" matches every bank/city when All is selected
d["D4"], d["D5"] = '=IF(B4="All","*",B4)', '=IF(B5="All","*",B5)'
d["C4"], d["C5"] = "filter →", "filter →"
for c in ("C4", "C5", "D4", "D5"):
    d[c].font = Font(color="9AA5B1", size=8)

# KPI summary
FIRST, LAST = 12, 61               # weekly table rows (room for 50 weeks)
d["F4"], d["F5"], d["F6"], d["F7"] = "Latest week", "Success value (₹ lakh)", "Change vs previous week", "Failure rate"
d["G4"] = f'=IFERROR(MAX(A{FIRST}:A{LAST}),"")'
d["G5"] = f'=IFERROR(INDEX(E{FIRST}:E{LAST},MATCH(G4,A{FIRST}:A{LAST},0)),"")'
d["G6"] = f'=IFERROR(INDEX(F{FIRST}:F{LAST},MATCH(G4,A{FIRST}:A{LAST},0)),"")'
d["G7"] = f'=IFERROR(INDEX(D{FIRST}:D{LAST},MATCH(G4,A{FIRST}:A{LAST},0)),"")'
d["F8"], d["G8"] = "Weeks with failure rate > 10%", f'=COUNTIF(D{FIRST}:D{LAST},">0.1")'
for r in range(4, 9):
    d[f"F{r}"].font = Font(bold=True)
    d[f"G{r}"].fill = PatternFill("solid", fgColor=BLUE_FILL)
d["G4"].number_format = "dd-mmm-yyyy"; d["G5"].number_format = "#,##0.0"
d["G6"].number_format = "+0.0%;-0.0%;0.0%"; d["G7"].number_format = "0.0%"

# Weekly table
heads = ["Week start", "Attempts", "Failed", "Failure rate", "Success value (₹ lakh)", "WoW change", "Status"]
for j, h in enumerate(heads):
    c = d.cell(row=FIRST - 1, column=j + 1, value=h)
    c.font, c.fill, c.alignment = hdr_font, hdr_fill, Alignment(horizontal="center", wrap_text=True)
for i, r in enumerate(range(FIRST, LAST + 1)):
    if i == 0:
        d[f"A{r}"] = "=IFERROR(MIN(Data!A:A),\"\")"
    else:
        d[f"A{r}"] = f'=IF(A{r-1}="","",IF(A{r-1}+7<=MAX(Data!A:A),A{r-1}+7,""))'
    d[f"B{r}"] = f'=IF(A{r}="","",SUMIFS(Data!D:D,Data!A:A,A{r},Data!B:B,$D$4,Data!C:C,$D$5))'
    d[f"C{r}"] = f'=IF(A{r}="","",SUMIFS(Data!E:E,Data!A:A,A{r},Data!B:B,$D$4,Data!C:C,$D$5))'
    d[f"D{r}"] = f'=IF(A{r}="","",IFERROR(C{r}/B{r},0))'
    d[f"E{r}"] = f'=IF(A{r}="","",SUMIFS(Data!F:F,Data!A:A,A{r},Data!B:B,$D$4,Data!C:C,$D$5)/100000)'
    d[f"F{r}"] = "" if i == 0 else f'=IF(OR(A{r}="",A{r-1}=""),"",IFERROR(E{r}/E{r-1}-1,""))'
    d[f"G{r}"] = f'=IF(A{r}="","",IF(D{r}>0.1,"ALERT: failures > 10%",IF(AND(ISNUMBER(F{r}),F{r}<-0.1),"Watch: value down >10%","OK")))'
    d[f"A{r}"].number_format = "dd-mmm-yyyy"; d[f"B{r}"].number_format = d[f"C{r}"].number_format = "#,##0"
    d[f"D{r}"].number_format = "0.0%"; d[f"E{r}"].number_format = "#,##0.0"; d[f"F{r}"].number_format = "+0.0%;-0.0%;0.0%"
    for col in "ABCDEFG":
        d[f"{col}{r}"].border = thin
red = PatternFill("solid", fgColor="FBEBEB")
d.conditional_formatting.add(f"A{FIRST}:G{LAST}", FormulaRule(formula=[f'AND($D{FIRST}<>"",$D{FIRST}>0.1)'], fill=red))
for col, w in zip("ABCDEFG", [14, 11, 10, 12, 20, 12, 24]):
    d.column_dimensions[col].width = w
d.column_dimensions["F"].width = 28; d.column_dimensions["G"].width = 24

chart = LineChart()
chart.title = "Successful recharge value per week (₹ lakh)"
chart.y_axis.title = "₹ lakh"; chart.x_axis.number_format = "dd-mmm"; chart.height, chart.width = 7.5, 17
chart.add_data(Reference(d, min_col=5, min_row=FIRST - 1, max_row=FIRST + len(df.week_start.unique()) - 1), titles_from_data=True)
chart.set_categories(Reference(d, min_col=1, min_row=FIRST, max_row=FIRST + len(df.week_start.unique()) - 1))
chart.legend = None
d.add_chart(chart, "I4")
d.freeze_panes = f"A{FIRST}"
wb.active = 1

out = ROOT / "excel" / "Recharge_Weekly_KPI.xlsx"
wb.save(out)
print("saved", out, "| data rows:", len(df), "| weeks:", df.week_start.nunique())
