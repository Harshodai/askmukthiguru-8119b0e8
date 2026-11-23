"""Strict three-tab Excel workbook generator using xlsxwriter matching the keyword-research specification."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import xlsxwriter

from services.keyword_research.models import KDLevel, KeywordResearchPayload, Priority


def create_keyword_research_workbook(
    payload: KeywordResearchPayload,
    output_path: Path,
) -> Path:
    """Generate the exact three-tab Excel workbook deliverable."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = xlsxwriter.Workbook(str(output_path))

    # Color palettes & formatting styles
    header_format = workbook.add_format({
        "bold": True,
        "bg_color": "#1F4E78",
        "font_color": "#FFFFFF",
        "border": 1,
        "align": "left",
        "valign": "vcenter",
    })
    total_format = workbook.add_format({
        "bold": True,
        "bg_color": "#D9E1F2",
        "border": 1,
        "align": "left",
        "valign": "vcenter",
    })
    currency_format = workbook.add_format({"num_format": "$#,##0.00"})
    int_format = workbook.add_format({"num_format": "#,##0"})
    pct_format = workbook.add_format({"num_format": "0.0%"})

    # Priority conditional formats
    prio_high = workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100", "bold": True})
    prio_med = workbook.add_format({"bg_color": "#FFEB9C", "font_color": "#9C6500"})
    prio_low = workbook.add_format({"bg_color": "#EFEFEF", "font_color": "#7F7F7F"})

    # KD level formats
    kd_easy = workbook.add_format({"bg_color": "#E2EFDA", "font_color": "#385723"})
    kd_med = workbook.add_format({"bg_color": "#FFF2CC", "font_color": "#B25900"})
    kd_hard = workbook.add_format({"bg_color": "#FCE4D6", "font_color": "#C65911"})

    # -------------------------------------------------------------
    # TAB 1: Topic Cluster Summary
    # -------------------------------------------------------------
    ws1 = workbook.add_worksheet("Topic Cluster Summary")
    ws1.freeze_panes(1, 0)

    # Compute aggregates per cluster
    clusters_data = defaultdict(lambda: {
        "count": 0,
        "vol": 0,
        "g_vol": 0,
        "kd_sum": 0,
        "cpc_sum": 0.0,
        "high": 0,
        "med": 0,
        "low": 0,
    })

    total_vol = sum(k.monthly_volume for k in payload.keywords)
    for kw in payload.keywords:
        c = clusters_data[kw.topic_cluster]
        c["count"] += 1
        c["vol"] += kw.monthly_volume
        c["g_vol"] += kw.global_volume
        c["kd_sum"] += kw.kd
        c["cpc_sum"] += kw.cpc
        if kw.priority == Priority.HIGH:
            c["high"] += 1
        elif kw.priority == Priority.MEDIUM:
            c["med"] += 1
        else:
            c["low"] += 1

    headers_tab1 = [
        "Topic Cluster",
        "Keywords (Count)",
        payload.volume_scope_label,
        "Global Volume",
        "Avg KD",
        "Avg CPC ($)",
        "High Priority",
        "Medium Priority",
        "Low Priority",
    ]
    for col_idx, h in enumerate(headers_tab1):
        ws1.write(0, col_idx, h, header_format)

    row = 1
    total_count = len(payload.keywords)
    total_gvol = sum(k.global_volume for k in payload.keywords)
    total_high = sum(1 for k in payload.keywords if k.priority == Priority.HIGH)
    total_med = sum(1 for k in payload.keywords if k.priority == Priority.MEDIUM)
    total_low = sum(1 for k in payload.keywords if k.priority == Priority.LOW)
    total_kd_avg = round(sum(k.kd for k in payload.keywords) / total_count, 1) if total_count else 0
    total_cpc_avg = round(sum(k.cpc for k in payload.keywords) / total_count, 2) if total_count else 0

    for cluster_name, stats in clusters_data.items():
        cnt = stats["count"]
        avg_kd = round(stats["kd_sum"] / cnt, 1) if cnt else 0
        avg_cpc = round(stats["cpc_sum"] / cnt, 2) if cnt else 0
        share = (stats["vol"] / total_vol) if total_vol else 0

        cluster_label_with_share = f"{cluster_name} ({share:.1%} volume share)"
        ws1.write(row, 0, cluster_label_with_share)
        ws1.write(row, 1, cnt, int_format)
        ws1.write(row, 2, stats["vol"], int_format)
        ws1.write(row, 3, stats["g_vol"], int_format)
        ws1.write(row, 4, avg_kd)
        ws1.write(row, 5, avg_cpc, currency_format)
        ws1.write(row, 6, stats["high"], int_format)
        ws1.write(row, 7, stats["med"], int_format)
        ws1.write(row, 8, stats["low"], int_format)
        row += 1

    # TOTAL Row
    ws1.write(row, 0, "TOTAL", total_format)
    ws1.write(row, 1, total_count, total_format)
    ws1.write(row, 2, total_vol, total_format)
    ws1.write(row, 3, total_gvol, total_format)
    ws1.write(row, 4, total_kd_avg, total_format)
    ws1.write(row, 5, total_cpc_avg, total_format)
    ws1.write(row, 6, total_high, total_format)
    ws1.write(row, 7, total_med, total_format)
    ws1.write(row, 8, total_low, total_format)

    ws1.set_column(0, 0, 42)
    ws1.set_column(1, 8, 16)

    # -------------------------------------------------------------
    # TAB 2: Priority Keyword Targets (300 Keywords)
    # -------------------------------------------------------------
    ws2 = workbook.add_worksheet("Priority Keyword Targets")
    ws2.freeze_panes(1, 0)

    headers_tab2 = [
        "Keyword",
        "Topic Cluster",
        "Search Intent",
        payload.volume_scope_label,
        "Global Volume",
        "KD",
        "KD Level",
        "CPC ($)",
        "Parent Topic",
        "Recommended Content Type",
        "Priority",
    ]
    for col_idx, h in enumerate(headers_tab2):
        ws2.write(0, col_idx, h, header_format)

    for r_idx, kw in enumerate(payload.keywords, start=1):
        ws2.write(r_idx, 0, kw.keyword)
        ws2.write(r_idx, 1, kw.topic_cluster)
        ws2.write(r_idx, 2, kw.search_intent.value)
        ws2.write(r_idx, 3, kw.monthly_volume, int_format)
        ws2.write(r_idx, 4, kw.global_volume, int_format)
        ws2.write(r_idx, 5, kw.kd, int_format)

        # KD Level color
        kd_style = kd_easy if kw.kd_level == KDLevel.EASY else (kd_med if kw.kd_level == KDLevel.MEDIUM else kd_hard)
        ws2.write(r_idx, 6, kw.kd_level.value, kd_style)

        ws2.write(r_idx, 7, kw.cpc, currency_format)
        ws2.write(r_idx, 8, kw.parent_topic)
        ws2.write(r_idx, 9, kw.content_type)

        # Priority color
        prio_style = prio_high if kw.priority == Priority.HIGH else (prio_med if kw.priority == Priority.MEDIUM else prio_low)
        ws2.write(r_idx, 10, kw.priority.value, prio_style)

    ws2.set_column(0, 0, 36)
    ws2.set_column(1, 1, 32)
    ws2.set_column(2, 2, 16)
    ws2.set_column(3, 7, 14)
    ws2.set_column(8, 9, 22)
    ws2.set_column(10, 10, 14)

    # -------------------------------------------------------------
    # TAB 3: Competitor & Gap Analysis
    # -------------------------------------------------------------
    ws3 = workbook.add_worksheet("Competitor & Gap Analysis")

    title_sec1 = workbook.add_format({"bold": True, "font_size": 13, "font_color": "#1F4E78"})

    # Section 1: Top 20 Organic Competitors
    ws3.write(0, 0, "SECTION 1: TOP 20 ORGANIC COMPETITORS", title_sec1)
    headers_sec1 = ["Competitor Domain", "Est. Traffic Share %", "Est. Traffic Value ($)", "Domain Rating (DR)", "Observations"]
    for c_idx, h in enumerate(headers_sec1):
        ws3.write(1, c_idx, h, header_format)

    row_s1 = 2
    for comp in payload.competitors:
        ws3.write(row_s1, 0, comp.domain)
        ws3.write(row_s1, 1, comp.traffic_share_pct / 100.0, pct_format)
        ws3.write(row_s1, 2, comp.traffic_value, currency_format)
        ws3.write(row_s1, 3, comp.domain_rating, int_format)
        ws3.write(row_s1, 4, comp.observations)
        row_s1 += 1

    # Section 2: 20 High-Value Keyword Gaps
    row_s2_title = row_s1 + 2
    ws3.write(row_s2_title, 0, "SECTION 2: 20 HIGH-VALUE KEYWORD GAPS & ACTIONS", title_sec1)
    headers_sec2 = ["Competitor Keyword Opportunity", "Top Ranking Competitor", payload.volume_scope_label, "KD", "Recommended Action"]
    for c_idx, h in enumerate(headers_sec2):
        ws3.write(row_s2_title + 1, c_idx, h, header_format)

    row_s2 = row_s2_title + 2
    for gap in payload.gaps:
        ws3.write(row_s2, 0, gap.competitor_keyword)
        ws3.write(row_s2, 1, gap.top_competitor)
        ws3.write(row_s2, 2, gap.volume, int_format)
        ws3.write(row_s2, 3, gap.kd, int_format)
        ws3.write(row_s2, 4, gap.recommended_action)
        row_s2 += 1

    # Section 3: Strategic Insights
    row_s3_title = row_s2 + 2
    ws3.write(row_s3_title, 0, "SECTION 3: STRATEGIC INSIGHTS & ROADMAP", title_sec1)

    ws3.write(row_s3_title + 1, 0, "5 Key Findings:", total_format)
    for f_idx, f_text in enumerate(payload.findings, start=row_s3_title + 2):
        ws3.write(f_idx, 0, f_text)

    rec_start = row_s3_title + 2 + len(payload.findings) + 1
    ws3.write(rec_start, 0, "5 Prioritized Recommendations:", total_format)
    for r_idx, r_text in enumerate(payload.recommendations, start=rec_start + 1):
        ws3.write(r_idx, 0, r_text)

    ws3.set_column(0, 0, 38)
    ws3.set_column(1, 1, 22)
    ws3.set_column(2, 3, 16)
    ws3.set_column(4, 4, 60)

    workbook.close()
    return output_path
