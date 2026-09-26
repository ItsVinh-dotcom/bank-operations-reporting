"""Generate the report pages (PBIR format) of DLB_Operations_Dashboard.

Run with Power BI Desktop CLOSED, then reopen the .pbip:
    python powerbi/build_report.py

The semantic model (tables, relationships, DAX measures) lives in DLB_Operations_Dashboard.SemanticModel.
This script only (re)writes the report layer: theme + 6 pages of visuals.

Layout (canvas 1280 x 720):
    +-----------+------------------------------------------------------+
    | brand     | page title / subtitle                                |
    |-----------|------------------------------------------------------|
    | slicers   | KPI tiles (label, value, comparison line)            |
    |           |------------------------------------------------------|
    | as-of     | chart row 1                                          |
    | date      |------------------------------------------------------|
    |           | chart row 2                                          |
    +-----------+------------------------------------------------------+
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE / "DLB_Operations_Dashboard.Report"
DEF = REPORT / "definition"
VC_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json"
PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
PAGES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json"

W, H = 1280, 720
SIDE_W = 200                      # left filter panel
CX, CW = SIDE_W + 16, W - SIDE_W - 32   # content area x / width (216 / 1048)
GAP = 10
TILE_Y, TILE_H = 64, 92
ROW1_Y, ROW2_Y, ROW_H = 166, 444, 268

NAVY, TEAL, AMBER, RED, GREY, LIGHT = "#0B3C5D", "#1D7874", "#F2A541", "#C0392B", "#6B7280", "#D6E4F0"
M = "_Measures"


# ----------------------------------------------------------------------------- helpers
def uid(*parts: str) -> str:
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:20]


def lit(v):
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, int):
        s = f"{v}L"
    elif isinstance(v, float):
        s = f"{v}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": s}}}


def color(hexv):
    return {"solid": {"color": lit(hexv)}}


def props(**kw):
    return [{"properties": {k: (v if isinstance(v, dict) else lit(v)) for k, v in kw.items()}}]


def meas(name):
    return {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": M}}, "Property": name}},
            "queryRef": f"{M}.{name}", "nativeQueryRef": name}


def col(table, name):
    return {"field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}},
            "queryRef": f"{table}.{name}", "nativeQueryRef": name}


def sort_def(field_proj, direction="Ascending"):
    return {"sort": [{"field": field_proj["field"], "direction": direction}], "isDefaultSort": True}


NO_FRAME = {"background": props(show=False), "border": props(show=False), "dropShadow": props(show=False),
            "title": props(show=False), "subTitle": props(show=False),
            "padding": props(top=0.0, bottom=0.0, left=0.0, right=0.0)}


def framed_title(text):
    return {"title": props(show=True, text=text, fontColor=color(NAVY), fontSize=11.0, bold=True),
            "subTitle": props(show=False), "dropShadow": props(show=False)}


def para(text, size, colr, bold=False, align="left"):
    style = {"fontSize": f"{size}pt", "color": colr}
    if bold:
        style["fontWeight"] = "bold"
    return {"textRuns": [{"value": text, "textStyle": style}], "horizontalTextAlignment": align}


def year_filter(page_key):
    """Page-level filter DimDate[Năm] >= 2024 (Dec-2023 only exists as the opening balance)."""
    return {"name": uid(page_key, "yearfilter"),
            "field": {"Column": {"Expression": {"SourceRef": {"Entity": "DimDate"}}, "Property": "Năm"}},
            "type": "Advanced",
            "filter": {"Version": 2, "From": [{"Name": "d", "Entity": "DimDate", "Type": 0}],
                       "Where": [{"Condition": {"Comparison": {
                           "ComparisonKind": 2,
                           "Left": {"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": "Năm"}},
                           "Right": {"Literal": {"Value": "2024L"}}}}}]},
            "howCreated": "User"}


def window_filter(page_key, vkey, measure):
    """Visual-level filter [measure] = 1 (e.g. 'Hiển thị 13 tháng': last 13 months inside the slicer range)."""
    return {"name": uid(page_key, vkey, "window"),
            "field": {"Measure": {"Expression": {"SourceRef": {"Entity": M}}, "Property": measure}},
            "type": "Advanced",
            "filter": {"Version": 2, "From": [{"Name": "m", "Entity": M, "Type": 0}],
                       "Where": [{"Condition": {"Comparison": {
                           "ComparisonKind": 0,
                           "Left": {"Measure": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": measure}},
                           "Right": {"Literal": {"Value": "1L"}}}}}]},
            "howCreated": "User"}


# axis / legend presets
AX_TIME = {"categoryAxis": props(showAxisTitle=False, fontSize=8.0, preferredCategoryWidth=16.0),
           "valueAxis": props(showAxisTitle=False, fontSize=8.0, labelDisplayUnits=1.0, labelPrecision=0)}
AX_CAT = {"categoryAxis": props(showAxisTitle=False, fontSize=8.0, preferredCategoryWidth=14.0),
          "valueAxis": props(showAxisTitle=False, fontSize=8.0, labelDisplayUnits=1.0, show=False)}
LEGEND_TOP = {"legend": props(show=True, position="Top", fontSize=8.0)}
LEGEND_OFF = {"legend": props(show=False)}
LABELS = {"labels": props(show=True, fontSize=8.0, labelDisplayUnits=1.0, color=color("#374151"))}

MONTH = col("DimDate", "Tháng (ngắn)")    # "8/26" labels; trend charts are windowed to recent months
DAY = col("DimDate", "Ngày")
BRANCH = col("DimBranch", "Chi nhánh")
PRODUCT = col("DimProduct", "Sản phẩm")


# ----------------------------------------------------------------------------- page builder
class Page:
    def __init__(self, key, display):
        self.key, self.display, self.visuals, self.z = key, display, [], 0

    def add(self, key, vtype, x, y, w, h, query=None, objects=None, vco=None, sort=None, filters=None):
        self.z += 1
        visual = {"visualType": vtype}
        if query:
            visual["query"] = {"queryState": query}
            if sort:
                visual["query"]["sortDefinition"] = sort
        if objects:
            visual["objects"] = objects
        if vco:
            visual["visualContainerObjects"] = vco
        visual["drillFilterOtherVisuals"] = True
        name = uid(self.key, key)
        self.visuals.append((name, {"$schema": VC_SCHEMA, "name": name,
                                    "position": {"x": x, "y": y, "z": self.z * 1000, "height": h, "width": w,
                                                 "tabOrder": self.z * 1000},
                                    "visual": visual}))
        if filters:
            self.visuals[-1][1]["filterConfig"] = {"filters": filters}

    def textbox(self, key, x, y, w, h, paragraphs, bg=None, border=False, pad=None):
        vco = dict(NO_FRAME)
        if pad:  # (top, left) inner padding in px
            vco["padding"] = props(top=float(pad[0]), left=float(pad[1]), right=float(pad[1]), bottom=0.0)
        if bg:
            vco["background"] = props(show=True, color=color(bg), transparency=0.0)
        if border:
            vco["border"] = props(show=True, color=color("#E5E7EB"), radius=8.0)
        self.add(key, "textbox", x, y, w, h, objects={"general": [{"properties": {"paragraphs": paragraphs}}]},
                 vco=vco)

    # ---- frame: sidebar + title
    def frame(self, title, subtitle, slicers=True):
        self.textbox("side_panel", 0, 0, SIDE_W, H, [para(" ", 8, GREY)], bg="#FFFFFF")
        self.textbox("brand", 0, 0, SIDE_W, 84,
                     [para("ĐÔNG LAM BANK", 13, "#FFFFFF", bold=True), para("Hệ thống báo cáo vận hành", 8.5, LIGHT)],
                     bg=NAVY, pad=(18, 16))
        self.textbox("filter_lbl", 16, 98, SIDE_W - 24, 24, [para("BỘ LỌC", 8.5, GREY, bold=True)])
        fields = [("DimDate", "Năm")]
        if slicers:
            fields += [("DimBranch", "Vùng"), ("DimBranch", "Chi nhánh")]
        for i, (t, c) in enumerate(fields):
            self.add(f"slicer_{c}", "slicer", 12, 124 + i * 66, SIDE_W - 24, 58,
                     query={"Values": {"projections": [col(t, c)]}},
                     objects={"data": props(mode="Dropdown"),
                              "header": props(show=True, fontColor=color(NAVY), textSize=10.0),
                              "items": props(textSize=10.0)},
                     vco=dict(NO_FRAME))
        # as-of date
        self.textbox("asof_lbl", 12, 588, SIDE_W - 24, 22, [para("Số liệu đến ngày", 8.5, GREY, bold=True)])
        self.add("asof", "card", 12, 606, SIDE_W - 24, 44, query={"Values": {"projections": [meas("Ngày dữ liệu")]}},
                 objects={"labels": props(color=color(NAVY), fontSize=15.0),
                          "categoryLabels": props(show=False)},
                 vco=dict(NO_FRAME))
        self.textbox("unit_note", 12, 654, SIDE_W - 24, 60,
                     [para("Đơn vị tiền: tỷ đồng", 8.5, GREY),
                      para("Biểu đồ xu hướng: 13 tháng gần nhất", 8, GREY),
                      para("Dữ liệu giả lập, ngân hàng hư cấu", 8, "#9CA3AF")])
        # page title
        self.textbox("title", CX, 4, CW, 58, [para(title, 15, NAVY, bold=True), para(subtitle, 9, GREY)],
                     pad=(6, 4))

    # ---- KPI tiles: label + value + comparison line
    def tiles(self, items):
        """items = [(label, value_measure, note_measure_or_None), ...]"""
        n = len(items)
        w = (CW - GAP * (n - 1)) / n
        for i, (label, vm, nm) in enumerate(items):
            x = round(CX + i * (w + GAP))
            ww = round(w)
            k = f"tile{i}"
            self.textbox(f"{k}_bg", x, TILE_Y, ww, TILE_H, [para(" ", 8, GREY)], bg="#FFFFFF", border=True)
            self.textbox(f"{k}_lbl", x + 4, TILE_Y + 8, ww - 8, 20, [para(label, 9, GREY, align="center")])
            self.add(f"{k}_val", "card", x + 4, TILE_Y + 28, ww - 8, 38,
                     query={"Values": {"projections": [meas(vm)]}},
                     objects={"labels": props(color=color(NAVY), fontSize=17.0, labelDisplayUnits=1.0),
                              "categoryLabels": props(show=False)},
                     vco=dict(NO_FRAME))
            if nm:
                self.add(f"{k}_note", "card", x + 4, TILE_Y + 66, ww - 8, 20,
                         query={"Values": {"projections": [meas(nm)]}},
                         objects={"labels": props(color=color(TEAL), fontSize=8.0),
                                  "categoryLabels": props(show=False)},
                         vco=dict(NO_FRAME))

    # ---- charts
    def chart(self, key, vtype, x, y, w, h, title, category, values=(), series=None, y2=(), time=True,
              labels=False, sort_measure=None, legend=None, window="Hiển thị 13 tháng"):
        q = {"Category": {"projections": [category]}}
        if values:
            q["Y"] = {"projections": [meas(v) for v in values]}
        if y2:
            q["Y2"] = {"projections": [meas(v) for v in y2]}
        if series:
            q["Series"] = {"projections": [series]}
        obj = dict(AX_TIME if time else AX_CAT)
        multi = len(values) + len(y2) > 1 or series is not None
        obj.update(LEGEND_TOP if (legend if legend is not None else multi) else LEGEND_OFF)
        if labels:
            obj.update(LABELS)
        if sort_measure:
            sort = sort_def(meas(sort_measure), "Descending")
        else:
            sort = sort_def(category, "Ascending")
        filters = [window_filter(self.key, key, window)] if (time and window) else None
        self.add(key, vtype, x, y, w, h, query=q, objects=obj, vco=framed_title(title), sort=sort, filters=filters)

    def table(self, key, x, y, w, h, title, spec, sort_measure=None):
        """spec = [(projection, header, relative_width), ...]; widths are scaled to fill the visual exactly,
        so the table never needs a horizontal scrollbar."""
        avail = w - 34                      # inner padding + vertical scrollbar
        total = sum(r for _, _, r in spec)
        proj, widths = [], []
        for pr, header, rel in spec:
            pr = dict(pr, displayName=header)
            proj.append(pr)
            widths.append({"properties": {"value": lit(round(avail * rel / total, 1))},
                           "selector": {"metadata": pr["queryRef"]}})
        self.add(key, "tableEx", x, y, w, h, query={"Values": {"projections": proj}},
                 objects={"columnHeaders": props(fontColor=color(NAVY), bold=True, fontSize=8.5, wordWrap=True,
                                                 autoSizeColumnWidth=False),
                          "values": props(fontSize=8.5, wordWrap=True),
                          "total": props(fontSize=8.5, bold=True),
                          "columnWidth": widths},
                 vco=framed_title(title),
                 sort=sort_def(meas(sort_measure), "Descending") if sort_measure else None)

    def matrix(self, key, x, y, w, h, title, rows, columns, values):
        self.add(key, "pivotTable", x, y, w, h,
                 query={"Rows": {"projections": [rows]}, "Columns": {"projections": [columns]},
                        "Values": {"projections": [meas(v) for v in values]}},
                 objects={"columnHeaders": props(fontColor=color(NAVY), bold=True, fontSize=8.0, wordWrap=True),
                          "rowHeaders": props(fontSize=8.0), "values": props(fontSize=8.0)},
                 vco=framed_title(title))


def cols(n):
    """x positions / width for n equal columns in the content area."""
    w = (CW - GAP * (n - 1)) / n
    return [round(CX + i * (w + GAP)) for i in range(n)], round(w)


# ----------------------------------------------------------------------------- pages
def build_pages() -> list[Page]:
    (x1, x2), w2 = cols(2)
    (t1, t2, t3), w3 = cols(3)
    pages = []

    # 1 ---------------------------------------------------------------- Executive overview
    p = Page("overview", "1. Tổng quan")
    p.frame("Tổng quan hoạt động kinh doanh",
            "Quy mô, chất lượng tài sản và mức hoàn thành kế hoạch · số dư cuối kỳ theo bộ lọc")
    p.tiles([("Tổng huy động", "Tổng huy động", "Nhãn · Tổng huy động"),
             ("Dư nợ cho vay", "Dư nợ", "Nhãn · Dư nợ"),
             ("Tỷ lệ CASA", "Tỷ lệ CASA", "Nhãn · Tỷ lệ CASA"),
             ("Tỷ lệ nợ xấu", "Tỷ lệ nợ xấu", "Nhãn · Tỷ lệ nợ xấu"),
             ("LDR (dư nợ / huy động)", "LDR", "Nhãn · LDR"),
             ("Khách hàng mới (YTD)", "Khách hàng mới YTD", "Nhãn · Khách hàng mới")])
    p.chart("trend", "lineChart", x1, ROW1_Y, w2, ROW_H, "Huy động và dư nợ cuối tháng (tỷ đồng)", MONTH,
            ["Tổng huy động", "Dư nợ"])
    p.chart("npl", "lineChart", x2, ROW1_Y, w2, ROW_H, "Tỷ lệ nợ xấu và nợ nhóm 2", MONTH,
            ["Tỷ lệ nợ xấu", "Tỷ lệ nợ nhóm 2"])
    p.table("branch_kpi", x1, ROW2_Y, w2, ROW_H, "Kết quả theo chi nhánh",
            [(BRANCH, "Chi nhánh", 30), (meas("Tổng huy động"), "Huy động", 18), (meas("% HT KH huy động"), "% KH huy động", 15),
             (meas("Dư nợ"), "Dư nợ", 18), (meas("% HT KH dư nợ"), "% KH dư nợ", 15), (meas("Tỷ lệ nợ xấu"), "Tỷ lệ NPL", 13)],
            sort_measure="Dư nợ")
    p.chart("newcust", "clusteredColumnChart", x2, ROW2_Y, w2, ROW_H, "Khách hàng mới so với kế hoạch", MONTH,
            ["Khách hàng mới", "Kế hoạch khách hàng mới"])
    pages.append(p)

    # 2 ---------------------------------------------------------------- Deposits
    p = Page("deposits", "2. Huy động")
    p.frame("Huy động vốn", "CASA = tiền gửi không kỳ hạn (vốn rẻ) · Có kỳ hạn = tiền gửi tiết kiệm/có kỳ hạn")
    p.tiles([("Tổng huy động", "Tổng huy động", "Nhãn · Tổng huy động"),
             ("CASA", "CASA", "Nhãn · CASA"),
             ("Tiền gửi có kỳ hạn", "Tiền gửi có kỳ hạn", "Nhãn · Tiền gửi có kỳ hạn"),
             ("Tỷ lệ CASA", "Tỷ lệ CASA", "Nhãn · Tỷ lệ CASA"),
             ("Tăng trưởng so cùng kỳ", "Tăng trưởng huy động YoY", "Nhãn · Tăng trưởng YoY"),
             ("% hoàn thành kế hoạch", "% HT KH huy động", None)])
    p.chart("mix", "columnChart", x1, ROW1_Y, w2, ROW_H, "Cơ cấu huy động cuối tháng (tỷ đồng)", MONTH,
            ["CASA", "Tiền gửi có kỳ hạn"])
    p.chart("casa_ratio", "lineChart", x2, ROW1_Y, w2, ROW_H, "Tỷ lệ CASA: nhích lên cuối quý do 'chạy số'", MONTH,
            ["Tỷ lệ CASA"])
    p.chart("daily", "lineChart", x1, ROW2_Y, w2, ROW_H, "Số dư huy động theo ngày (tỷ đồng)", DAY,
            ["Số dư huy động ngày"], series=col("DimProduct", "Loại sản phẩm"))
    p.table("branch_table", x2, ROW2_Y, w2, ROW_H, "Huy động theo chi nhánh",
            [(BRANCH, "Chi nhánh", 30), (meas("Tổng huy động"), "Tổng huy động", 20),
             (meas("Kế hoạch huy động"), "Kế hoạch", 20), (meas("% HT KH huy động"), "% HT KH", 15),
             (meas("Tỷ lệ CASA"), "Tỷ lệ CASA", 15)],
            sort_measure="Tổng huy động")
    pages.append(p)

    # 3 ---------------------------------------------------------------- Credit & risk
    p = Page("credit", "3. Tín dụng & Rủi ro")
    p.frame("Tín dụng & rủi ro", "Nợ xấu = nhóm 3-5 · nhóm nợ theo số ngày quá hạn, lấy nhóm cao hơn khi đối chiếu CIC")
    p.tiles([("Dư nợ cho vay", "Dư nợ", "Nhãn · Dư nợ"),
             ("Tăng trưởng tín dụng YTD", "Tăng trưởng tín dụng YTD", None),
             ("Nợ xấu (tỷ đồng)", "Nợ xấu", "Nhãn · Nợ xấu"),
             ("Tỷ lệ nợ xấu", "Tỷ lệ nợ xấu", "Nhãn · Tỷ lệ nợ xấu"),
             ("Tỷ lệ nợ nhóm 2", "Tỷ lệ nợ nhóm 2", None),
             ("Tỷ lệ bao phủ nợ xấu", "Tỷ lệ bao phủ nợ xấu", None)])
    p.chart("npl_branch", "clusteredBarChart", t1, ROW1_Y, w3, ROW_H, "Tỷ lệ nợ xấu theo chi nhánh", BRANCH,
            ["Tỷ lệ nợ xấu"], time=False, labels=True, sort_measure="Tỷ lệ nợ xấu")
    p.chart("npl_product", "clusteredBarChart", t2, ROW1_Y, w3, ROW_H, "Tỷ lệ nợ xấu theo sản phẩm", PRODUCT,
            ["Tỷ lệ nợ xấu (danh mục)"], time=False, labels=True, sort_measure="Tỷ lệ nợ xấu (danh mục)")
    p.chart("loan_mix", "clusteredBarChart", t3, ROW1_Y, w3, ROW_H, "Dư nợ theo sản phẩm (tỷ đồng)", PRODUCT,
            ["Dư nợ (danh mục)"], time=False, labels=True, sort_measure="Dư nợ (danh mục)")
    mw = 680
    p.matrix("migration", t1, ROW2_Y, mw, ROW_H, "Ma trận chuyển nhóm nợ (số khoản vay, cộng dồn kỳ đang lọc)",
             col("FactLoanMigration", "Nhóm đầu kỳ"), col("FactLoanMigration", "Nhóm cuối kỳ"),
             ["Số khoản vay chuyển nhóm"])
    p.chart("disb", "clusteredColumnChart", CX + mw + GAP, ROW2_Y, CW - mw - GAP, ROW_H, "Giải ngân mới theo tháng (tỷ đồng)", MONTH,
            ["Giải ngân mới"])
    pages.append(p)

    # 4 ---------------------------------------------------------------- Customers, cards & channels
    p = Page("channels", "4. Khách hàng, Thẻ & Kênh")
    p.frame("Khách hàng, thẻ & kênh số", "Chiến dịch thẻ Q2/2025: phát hành tăng mạnh nhưng tỷ lệ kích hoạt thấp")
    p.tiles([("Khách hàng hoạt động", "Khách hàng hoạt động", None),
             ("Khách hàng mới (YTD)", "Khách hàng mới YTD", "Nhãn · Khách hàng mới"),
             ("Tỷ trọng kênh số", "Tỷ trọng kênh số", None),
             ("Thẻ phát hành (lũy kế)", "Thẻ tín dụng phát hành", "Nhãn · Thẻ phát hành"),
             ("Tỷ lệ kích hoạt thẻ", "Tỷ lệ kích hoạt thẻ", None),
             ("Chi tiêu thẻ (lũy kế)", "Chi tiêu thẻ tín dụng", None)])
    p.chart("channel_mix", "hundredPercentStackedColumnChart", x1, ROW1_Y, w2, ROW_H, "Cơ cấu giao dịch theo kênh",
            MONTH, ["Số giao dịch"], series=col("FactChannel", "Kênh"))
    p.chart("card_campaign", "lineClusteredColumnComboChart", x2, ROW1_Y, w2, ROW_H,
            "Thẻ tín dụng phát hành (cột) và tỷ lệ kích hoạt (đường)", MONTH, ["Thẻ tín dụng phát hành"],
            y2=["Tỷ lệ kích hoạt thẻ"], window="Hiển thị 18 tháng")
    p.chart("mcc", "clusteredBarChart", x1, ROW2_Y, w2, ROW_H, "Chi tiêu thẻ theo ngành hàng (tỷ đồng)",
            col("FactCardSpend", "Ngành hàng"), ["Chi tiêu thẻ tín dụng"], time=False, labels=True,
            sort_measure="Chi tiêu thẻ tín dụng")
    p.chart("digital", "lineChart", x2, ROW2_Y, w2, ROW_H, "Tỷ trọng giao dịch qua kênh số", MONTH, ["Tỷ trọng kênh số"])
    pages.append(p)

    # 5 ---------------------------------------------------------------- Operations
    p = Page("operations", "5. Vận hành")
    p.frame("Vận hành: ATM, quầy giao dịch, khiếu nại", "Sự cố ATM cụm CN Sài Gòn 9-10/2025 · lỗi ứng dụng 3/2026")
    p.tiles([("Uptime ATM", "Uptime ATM", "Nhãn · Uptime ATM"),
             ("Sự cố ATM (lũy kế)", "Số sự cố ATM", None),
             ("Khiếu nại (lũy kế)", "Số khiếu nại", None),
             ("Tỷ lệ vi phạm SLA", "Tỷ lệ vi phạm SLA", "Nhãn · SLA"),
             ("Xử lý khiếu nại TB", "Thời gian xử lý TB (ngày LV)", None),
             ("Thời gian chờ TB", "Thời gian chờ TB (phút)", None)])
    p.chart("uptime", "lineChart", x1, ROW1_Y, w2, ROW_H, "Uptime ATM theo tháng", MONTH, ["Uptime ATM"])
    p.chart("atm_wd", "clusteredColumnChart", x2, ROW1_Y, w2, ROW_H, "Lượt rút tiền ATM (tăng vọt trước Tết)", MONTH,
            ["Lượt rút tiền ATM"])
    hw = (w2 - GAP) // 2
    p.chart("complaint_month", "columnChart", x1, ROW2_Y, w2, ROW_H, "Khiếu nại theo tháng và loại", MONTH,
            ["Số khiếu nại"], series=col("FactComplaint", "Loại khiếu nại"))
    p.chart("complaint_type", "clusteredBarChart", x2, ROW2_Y, hw, ROW_H, "Khiếu nại theo loại",
            col("FactComplaint", "Loại khiếu nại"), ["Số khiếu nại"], time=False, labels=True,
            sort_measure="Số khiếu nại")
    p.chart("wait", "clusteredBarChart", x2 + hw + GAP, ROW2_Y, w2 - hw - GAP, ROW_H, "Thời gian chờ tại quầy",
            BRANCH, ["Thời gian chờ TB (phút)"], time=False, labels=True, sort_measure="Thời gian chờ TB (phút)")
    pages.append(p)

    # 6 ---------------------------------------------------------------- Data quality
    p = Page("dq", "6. Chất lượng dữ liệu")
    p.frame("Chất lượng dữ liệu", "15 quy tắc kiểm tra tự động sau mỗi lô ETL · lỗi được cài sẵn để kiểm chứng",
            slicers=False)
    p.tiles([("Số bản ghi kiểm tra", "Số bản ghi kiểm tra", None),
             ("Số bản ghi lỗi", "Số bản ghi lỗi", None),
             ("Tỷ lệ lỗi", "Tỷ lệ lỗi", None),
             ("Số lô FAIL", "Số lô FAIL", None)])
    tw = 640
    p.table("dq_rules", CX, ROW1_Y, tw, ROW2_Y + ROW_H - ROW1_Y, "Kết quả theo quy tắc",
            [(col("FactDQ", "Mã quy tắc"), "Mã quy tắc", 20), (col("FactDQ", "Mô tả"), "Mô tả", 42),
             (col("FactDQ", "Mức độ"), "Mức độ", 11), (meas("Số bản ghi lỗi"), "Bản ghi lỗi", 11),
             (meas("Số lô FAIL"), "Lô FAIL", 8), (meas("Tỷ lệ lỗi"), "Tỷ lệ lỗi", 10)],
            sort_measure="Số bản ghi lỗi")
    rx, rw = CX + tw + GAP, CW - tw - GAP
    p.chart("dq_dim", "clusteredBarChart", rx, ROW1_Y, rw, ROW_H, "Bản ghi lỗi theo chiều chất lượng",
            col("FactDQ", "Chiều chất lượng"), ["Số bản ghi lỗi"], time=False, labels=True,
            sort_measure="Số bản ghi lỗi")
    p.chart("dq_month", "clusteredColumnChart", rx, ROW2_Y, rw, ROW_H, "Bản ghi lỗi theo tháng", MONTH,
            ["Số bản ghi lỗi"])
    pages.append(p)
    return pages


THEME = {
    "name": "DLB Banking",
    "dataColors": [NAVY, TEAL, AMBER, "#5B8DB8", RED, "#8E6C8A", "#7FB77E", "#B8B8B8", "#2E4A62", "#E07A5F"],
    "background": "#FFFFFF", "foreground": "#1F2937", "tableAccent": NAVY,
    "good": TEAL, "neutral": AMBER, "bad": RED,
    "textClasses": {"title": {"fontFace": "Segoe UI Semibold", "color": NAVY, "fontSize": 11},
                    "label": {"fontFace": "Segoe UI", "color": "#374151", "fontSize": 9}},
    "visualStyles": {
        "*": {"*": {"background": [{"show": True, "color": {"solid": {"color": "#FFFFFF"}}, "transparency": 0}],
                    "border": [{"show": True, "color": {"solid": {"color": "#E5E7EB"}}, "radius": 8}],
                    "dropShadow": [{"show": False}],
                    "subTitle": [{"show": False}]}},
        "page": {"*": {"background": [{"color": {"solid": {"color": "#F3F5F8"}}, "transparency": 0}]}},
    },
}


def write():
    pages_dir = DEF / "pages"
    if pages_dir.exists():
        shutil.rmtree(pages_dir)
    pages_dir.mkdir(parents=True)
    pages = build_pages()
    order = []
    for pg in pages:
        pname = uid("page", pg.key)
        order.append(pname)
        pdir = pages_dir / pname
        (pdir / "visuals").mkdir(parents=True)
        (pdir / "page.json").write_text(json.dumps({
            "$schema": PAGE_SCHEMA, "name": pname, "displayName": pg.display, "displayOption": "FitToPage",
            "height": H, "width": W, "filterConfig": {"filters": [year_filter(pg.key)]}},
            ensure_ascii=False, indent=2), encoding="utf-8")
        for vname, vjson in pg.visuals:
            vdir = pdir / "visuals" / vname
            vdir.mkdir()
            (vdir / "visual.json").write_text(json.dumps(vjson, ensure_ascii=False, indent=2), encoding="utf-8")
    (pages_dir / "pages.json").write_text(json.dumps({"$schema": PAGES_SCHEMA, "pageOrder": order,
                                                      "activePageName": order[0]}, indent=2), encoding="utf-8")
    # custom theme
    res = REPORT / "StaticResources" / "RegisteredResources"
    res.mkdir(parents=True, exist_ok=True)
    (res / "DLB_Theme.json").write_text(json.dumps(THEME, ensure_ascii=False, indent=2), encoding="utf-8")
    rep_path = DEF / "report.json"
    rep = json.loads(rep_path.read_text(encoding="utf-8"))
    base = rep["themeCollection"]["baseTheme"]
    rep["themeCollection"]["customTheme"] = {"name": "DLB_Theme.json", "reportVersionAtImport": base.get("reportVersionAtImport"),
                                             "type": "RegisteredResources"}
    pkgs = [p for p in rep.get("resourcePackages", []) if p.get("name") != "RegisteredResources"]
    pkgs.append({"name": "RegisteredResources", "type": "RegisteredResources",
                 "items": [{"name": "DLB_Theme.json", "path": "DLB_Theme.json", "type": "CustomTheme"}]})
    rep["resourcePackages"] = pkgs
    rep_path.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    n = sum(len(p.visuals) for p in pages)
    print(f"wrote {len(pages)} pages, {n} visuals -> {pages_dir}")


if __name__ == "__main__":
    write()
