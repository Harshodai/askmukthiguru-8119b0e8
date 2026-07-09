#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

# Paths
BENCHMARK_DIR = Path(__file__).resolve().parent
REPORT_DIR = BENCHMARK_DIR / "reports"
DASHBOARD_PATH = REPORT_DIR / "dashboard.html"

def load_reports():
    ruthless_data = {}
    native_data = []
    comprehensive_data = {}
    
    ruthless_path = REPORT_DIR / "ruthless_report.json"
    if ruthless_path.exists():
        try:
            with open(ruthless_path) as f:
                ruthless_data = json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading ruthless report: {e}")
            
    native_path = REPORT_DIR / "native_eval_report.json"
    if native_path.exists():
        try:
            with open(native_path) as f:
                native_data = json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading native eval report: {e}")

    comp_path = REPORT_DIR / "comprehensive_report.json"
    if comp_path.exists():
        try:
            with open(comp_path) as f:
                comprehensive_data = json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading comprehensive report: {e}")
            
    return ruthless_data, native_data, comprehensive_data


def collect_docker_logs() -> dict[str, str]:
    """Collect docker compose logs for each service. Best-effort — returns empty on failure."""
    import subprocess
    services = ["backend", "celery-worker", "qdrant", "redis", "neo4j"]
    logs = {}
    for svc in services:
        try:
            ret = subprocess.run(
                ["docker", "compose", "logs", "--tail", "200", svc],
                capture_output=True, text=True, timeout=30,
            )
            if ret.returncode == 0 and ret.stdout.strip():
                logs[svc] = ret.stdout[-10000:]  # cap at ~10k chars
            else:
                logs[svc] = f"(no output or service not found: {ret.stderr[:200]})"
        except Exception as e:
            logs[svc] = f"(collection failed: {e})"
    return logs

def build_html(ruthless, native, comprehensive, docker_logs):
    # Overall Score calculations
    score = ruthless.get("production_readiness_score", 0.0)
    verdict = ruthless.get("verdict", "FAIL")
    timestamp = ruthless.get("timestamp", time.time())
    run_id = ruthless.get("run_id", "N/A")
    backend_url = ruthless.get("backend", "http://localhost:8000")
    
    formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
    
    infra = ruthless.get("infrastructure", [])
    results = ruthless.get("results", [])
    categories = ruthless.get("categories", {})
    
    # Calculate stats
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r.get("passed", False))
    failed_tests = total_tests - passed_tests
    pass_rate = (passed_tests / total_tests) if total_tests > 0 else 0.0
    
    latencies = [r.get("latency_ms", 0.0) for r in results if r.get("latency_ms") is not None]
    avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0.0
    
    # Category scores mapping
    category_rows_html = ""
    for cat_id, cat_data in categories.items():
        cat_score = cat_data.get("score", 0.0)
        cat_weight = cat_data.get("weight", 0.0)
        cat_verdict = cat_data.get("verdict", "FAIL")
        cat_name = cat_data.get("name", cat_id)
        
        status_class = "pass" if cat_verdict == "PASS" else "fail"
        status_dot = "🟢" if cat_verdict == "PASS" else "🔴"
        
        details_list = "".join(f"<li>{d}</li>" for d in cat_data.get("details", []))
        
        category_rows_html += f"""
        <div class="category-card {status_class}">
            <div class="category-header">
                <span class="category-title">{status_dot} {cat_name}</span>
                <span class="category-meta">Weight: {cat_weight:.0%}</span>
            </div>
            <div class="progress-bar-container">
                <div class="progress-bar" style="width: {cat_score:.0%}"></div>
            </div>
            <div class="category-score-value">{cat_score:.0%}</div>
            <ul class="category-details">
                {details_list}
            </ul>
        </div>
        """

    # Infrastructure status cards
    infra_cards_html = ""
    for inf in infra:
        is_up = inf.get("reachable", False)
        service_name = inf.get("service", "Unknown Service")
        lat = inf.get("latency_ms", 0.0)
        status_label = "🟢 ONLINE" if is_up else "🔴 OFFLINE"
        card_class = "infra-up" if is_up else "infra-down"
        err = inf.get("error", "")
        err_html = f'<div class="infra-error">{err}</div>' if err else ""
        
        infra_cards_html += f"""
        <div class="infra-card {card_class}">
            <div class="infra-service">{service_name}</div>
            <div class="infra-status">{status_label}</div>
            <div class="infra-latency">{lat:.1f} ms</div>
            {err_html}
        </div>
        """

    # Test Results Rows
    results_rows_html = ""
    for idx, r in enumerate(results):
        r_passed = r.get("passed", True)
        status_class = "row-pass" if r_passed else "row-fail"
        status_badge = "PASS" if r_passed else "FAIL"
        
        category = r.get("category", "")
        query = r.get("query", "")
        response = r.get("response", "")
        latency = r.get("latency_ms", 0.0)
        citations = r.get("citations", [])
        failure_type = r.get("failure_type", "")
        
        variant_type = r.get("variant_type")
        original_q = r.get("original_q")
        
        variant_tag_html = ""
        if variant_type:
            variant_tag_html = f'<span class="badge variant-{variant_type}">{variant_type.upper()} VARIANT</span>'
            
        original_q_html = ""
        if original_q:
            original_q_html = f'<div class="original-query">Original: "{original_q}"</div>'
            
        citations_html = ""
        if citations:
            cites_li = "".join(f"<li>{c}</li>" for c in citations)
            citations_html = f"""
            <div class="citations-container">
                <strong>Citations ({len(citations)}):</strong>
                <ul>{cites_li}</ul>
            </div>
            """
            
        trace_id = r.get("trace_id", "")
        error_str = r.get("error", "")
        backend_logs = r.get("backend_logs", "")

        node_timings = r.get("node_timings", {})
        timings_html = ""
        if node_timings:
            timings_items = "".join(f'<span class="timing-chip">{k}: {v:.0f}ms</span>' for k, v in node_timings.items())
            timings_html = f'<div class="timings-container">{timings_items}</div>'

        trace_html = ""
        if trace_id:
            trace_html = f'<div class="trace-info">🔗 Trace: <a href="http://localhost:16686/trace/{trace_id}" target="_blank" class="trace-link">{trace_id[:16]}</a></div>'

        error_html = ""
        if error_str:
            error_html = f'<div class="error-stack-box"><strong>Error:</strong><pre>{error_str}</pre></div>'
            
        fail_reason = ""
        if failure_type:
            fail_reason = f'<div class="fail-reason-box">⚠️ Failure: {failure_type.replace("_", " ").title()}</div>'
            
        metrics_grid = f"""
        <div class="metrics-grid">
            <div class="metric-item">
                <span class="m-label">Latency</span>
                <span class="m-val">{latency:.1f}ms</span>
            </div>
            <div class="metric-item">
                <span class="m-label">Keyword Score</span>
                <span class="m-val">{r.get("keyword_score", 0.0):.2f}</span>
            </div>
            <div class="metric-item">
                <span class="m-label">Faithfulness</span>
                <span class="m-val">{r.get("faithfulness", 0.0):.2f}</span>
            </div>
            <div class="metric-item">
                <span class="m-label">Relevancy</span>
                <span class="m-val">{r.get("answer_relevancy", 0.0):.2f}</span>
            </div>
        </div>
        """
        
        results_rows_html += f"""
        <div class="test-card {status_class}" data-category="{category}" data-status="{status_badge}" data-variant="{variant_type or 'original'}" data-search="{query.lower()} {response.lower()}">
            <div class="test-card-summary" onclick="toggleDetails(this)">
                <div class="test-meta">
                    <span class="badge status-{status_badge.lower()}">{status_badge}</span>
                    <span class="test-category-badge">{category}</span>
                    {variant_tag_html}
                    <span class="test-latency">{latency:.0f}ms</span>
                </div>
                <div class="test-query-summary">{query}</div>
            </div>
            <div class="test-card-details">
                {original_q_html}
                {fail_reason}
                {metrics_grid}
                {error_html}
                {trace_html}
                <div class="response-box">
                    <strong>Model Response:</strong>
                    <p>{response}</p>
                </div>
                {citations_html}
                {timings_html}
                <div class="debug-details">
                    <span>Intent: {r.get("intent", "N/A")}</span> | 
                    <span>Trace: {trace_id[:24] if trace_id else "N/A"}</span> | 
                    <span>Layer: {r.get("layer_tested", "N/A")}</span>
                </div>
            </div>
        </div>
        """

    # Native RAGAS Evaluator UI
    native_eval_html = ""
    if native:
        avg_sec = sum(r.get("security_score", 0.0) for r in native) / len(native)
        avg_prec = sum(r.get("precision", 0.0) for r in native) / len(native)
        avg_faith = sum(r.get("faithfulness", 0.0) for r in native) / len(native)
        avg_lat = sum(r.get("latency_s", 0.0) for r in native) / len(native)
        
        native_rows = ""
        for n in native:
            sec_val = f"{n.get('security_score', 0.0):.0%}"
            prec_val = f"{n.get('precision', 0.0):.0%}"
            faith_val = f"{n.get('faithfulness', 0.0):.0%}"
            
            native_rows += f"""
            <div class="native-eval-card">
                <div class="native-query">"{n.get('query')}"</div>
                <div class="native-meta">Category: {n.get('category')} | Latency: {n.get('latency_s'):.2f}s</div>
                <div class="native-scores">
                    <div class="native-score-chip">🛡️ Security: {sec_val}</div>
                    <div class="native-score-chip">🎯 Precision: {prec_val}</div>
                    <div class="native-score-chip">🔬 Faithfulness: {faith_val}</div>
                </div>
            </div>
            """
            
    # Latency Distribution Chart (SVG bar chart)
    latency_buckets = {"<1s": 0, "1-3s": 0, "3-5s": 0, "5-10s": 0, "10-30s": 0, ">30s": 0}
    for r in results:
        lat = r.get("latency_ms", 0) / 1000
        if lat < 1: latency_buckets["<1s"] += 1
        elif lat < 3: latency_buckets["1-3s"] += 1
        elif lat < 5: latency_buckets["3-5s"] += 1
        elif lat < 10: latency_buckets["5-10s"] += 1
        elif lat < 30: latency_buckets["10-30s"] += 1
        else: latency_buckets[">30s"] += 1
    max_bucket = max(latency_buckets.values()) or 1
    bar_height = 140
    bar_width = 55
    bars_svg = ""
    x = 10
    for label, count in latency_buckets.items():
        h = (count / max_bucket) * bar_height
        y = bar_height - h
        bars_svg += f'<rect x="{x}" y="{y}" width="{bar_width-10}" height="{max(h, 2)}" rx="3" fill="var(--primary)" opacity="0.8"><title>{count} queries ({label})</title></rect>'
        bars_svg += f'<text x="{x + (bar_width-10)/2}" y="{bar_height + 14}" text-anchor="middle" font-size="10" fill="var(--text-muted)">{label}</text>'
        bars_svg += f'<text x="{x + (bar_width-10)/2}" y="{y - 6}" text-anchor="middle" font-size="11" fill="var(--text-color)" font-weight="600">{count}</text>'
        x += bar_width
    chart_svg_width = x + 10

    # Docker logs section
    docker_logs_html = ""
    for svc in ["backend", "celery-worker", "qdrant", "redis", "neo4j"]:
        log_content = docker_logs.get(svc, "(no logs collected)")
        log_id = f"logs-{svc}"
        docker_logs_html += f"""
        <div class="docker-log-card">
            <div class="docker-log-header" onclick="toggleDetails(this)">
                <span class="docker-log-service">🐳 {svc}</span>
                <span class="docker-log-toggle">▼</span>
            </div>
            <div class="docker-log-body" id="{log_id}">
                <pre>{log_content[:8000]}</pre>
            </div>
        </div>"""

    # Comprehensive section
    comp_html = ""
    if comprehensive and comprehensive.get("results"):
        comp_total = comprehensive.get("total", 0)
        comp_passed = comprehensive.get("passed", 0)
        comp_rate = comp_passed / comp_total if comp_total else 0
        comp_rows = ""
        for cr in comprehensive["results"]:
            c_sym = "✅" if cr.get("passed") else "❌"
            c_q = cr.get("query", "")[:60]
            comp_rows += f"""
            <div class="test-card {'row-pass' if cr.get('passed') else 'row-fail'}">
                <div class="test-card-summary" onclick="toggleDetails(this)">
                    <div class="test-meta">
                        <span class="badge status-{'pass' if cr.get('passed') else 'fail'}">{'PASS' if cr.get('passed') else 'FAIL'}</span>
                        <span class="test-category-badge">{cr.get('category', '')}</span>
                        <span class="test-latency">{cr.get('latency_ms', 0):.0f}ms</span>
                    </div>
                    <div class="test-query-summary">{c_q}</div>
                </div>
                <div class="test-card-details">
                    <div class="metrics-grid">
                        <div class="metric-item"><span class="m-label">KW Score</span><span class="m-val">{cr.get('keyword_score', 0):.2f}</span></div>
                        <div class="metric-item"><span class="m-label">Intent</span><span class="m-val">{cr.get('intent', 'N/A')}</span></div>
                        <div class="metric-item"><span class="m-label">Intent Match</span><span class="m-val">{'✅' if cr.get('intent_match') else '❌'}</span></div>
                        <div class="metric-item"><span class="m-label">Difficulty</span><span class="m-val">{cr.get('difficulty', '')}</span></div>
                    </div>
                    {('<div class="fail-reason-box">Error: ' + cr.get('error', '') + '</div>') if cr.get('error') else ''}
                    <div class="response-box"><strong>Response:</strong><p>{cr.get('response', '')[:600]}</p></div>
                    {('<div class="citations-container"><strong>Citations:</strong><ul>' + ''.join(f'<li>{c}</li>' for c in cr.get('citations', [])) + '</ul></div>') if cr.get('citations') else ''}
                </div>
            </div>"""
        comp_html = f"""
        <div class="metrics-cards-row">
            <div class="metric-card"><span class="label">Tiered Tests</span><span class="value">{comp_total}</span></div>
            <div class="metric-card"><span class="label">Pass Rate</span><span class="value" style="color:var(--success)">{comp_rate:.0%}</span></div>
            <div class="metric-card"><span class="label">Failed</span><span class="value">{comp_total - comp_passed}</span></div>
            <div class="metric-card"><span class="label">5 Tiers</span><span class="value">Simple→Edge</span></div>
        </div>
        <div class="test-list">{comp_rows}</div>"""

        native_eval_html = f"""
        <div class="native-eval-section">
            <h2 class="section-title">🔬 Native RAGAS Metrics (LLM Evaluators)</h2>
            <div class="native-summary-grid">
                <div class="native-summary-card">
                    <div class="n-val">{avg_sec:.1%}</div>
                    <div class="n-lbl">Security Resistance</div>
                </div>
                <div class="native-summary-card">
                    <div class="n-val">{avg_prec:.1%}</div>
                    <div class="n-lbl">Context Precision</div>
                </div>
                <div class="native-summary-card">
                    <div class="n-val">{avg_faith:.1%}</div>
                    <div class="n-lbl">Context Faithfulness</div>
                </div>
                <div class="native-summary-card">
                    <div class="n-val">{avg_lat:.2f}s</div>
                    <div class="n-lbl">Average Eval Latency</div>
                </div>
            </div>
            <div class="native-list">
                {native_rows}
            </div>
        </div>
        """
    else:
        native_eval_html = """
        <div class="empty-state">
            ⚠️ No native RAGAS evaluation data found. Run `native_eval.py` to populate these metrics.
        </div>
        """

    # HTML string
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AskMukthiGuru — Readiness Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #08080f;
            --bg-gradient: linear-gradient(135deg, #08080f 0%, #0d0b21 100%);
            --panel-bg: rgba(255, 255, 255, 0.03);
            --panel-border: rgba(255, 255, 255, 0.08);
            --text-color: #e2e8f0;
            --text-muted: #94a3b8;
            --primary: #6366f1;
            --primary-glow: rgba(99, 102, 241, 0.4);
            --success: #10b981;
            --success-glow: rgba(16, 185, 129, 0.2);
            --warning: #f59e0b;
            --critical: #ef4444;
            --critical-glow: rgba(239, 68, 68, 0.2);
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background: var(--bg-color);
            background-image: var(--bg-gradient);
            color: var(--text-color);
            font-family: 'Inter', sans-serif;
            min-height: 100vh;
            padding: 2rem;
            line-height: 1.5;
        }}

        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2.5rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--panel-border);
        }}

        .brand {{
            display: flex;
            flex-direction: column;
        }}

        .brand h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: 2.25rem;
            font-weight: 700;
            background: linear-gradient(to right, #a5b4fc, #6366f1, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.25rem;
        }}

        .brand .meta {{
            color: var(--text-muted);
            font-size: 0.875rem;
            letter-spacing: 0.05em;
        }}

        .run-meta-pills {{
            display: flex;
            gap: 1rem;
            align-items: center;
        }}

        .pill {{
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            padding: 0.5rem 1rem;
            border-radius: 9999px;
            font-size: 0.8125rem;
            font-family: monospace;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .pill.verdict-pass {{
            border-color: var(--success);
            color: var(--success);
            box-shadow: 0 0 10px var(--success-glow);
        }}

        .pill.verdict-fail {{
            border-color: var(--critical);
            color: var(--critical);
            box-shadow: 0 0 10px var(--critical-glow);
        }}

        /* Tabs Layout */
        .tabs {{
            display: flex;
            gap: 1rem;
            margin-bottom: 2rem;
            border-bottom: 1px solid var(--panel-border);
            padding-bottom: 1px;
        }}

        .tab-btn {{
            background: none;
            border: none;
            color: var(--text-muted);
            font-family: 'Outfit', sans-serif;
            font-size: 1.1rem;
            font-weight: 500;
            padding: 0.75rem 1.5rem;
            cursor: pointer;
            position: relative;
            transition: var(--transition);
        }}

        .tab-btn.active {{
            color: var(--text-color);
        }}

        .tab-btn.active::after {{
            content: '';
            position: absolute;
            bottom: -1px;
            left: 0;
            right: 0;
            height: 2px;
            background: var(--primary);
            box-shadow: 0 0 10px var(--primary-glow);
        }}

        .tab-content {{
            display: none;
        }}

        .tab-content.active {{
            display: block;
            animation: fadeIn 0.4s ease;
        }}

        /* Grid layouts */
        .dashboard-grid {{
            display: grid;
            grid-template-columns: 320px 1fr;
            gap: 2rem;
        }}

        .sidebar {{
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }}

        /* Circular Score Ring */
        .score-panel {{
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 16px;
            padding: 2rem;
            text-align: center;
            backdrop-filter: blur(12px);
            display: flex;
            flex-direction: column;
            align-items: center;
        }}

        .score-ring-svg {{
            width: 160px;
            height: 160px;
            transform: rotate(-90deg);
        }}

        .score-ring-bg {{
            fill: none;
            stroke: rgba(255, 255, 255, 0.05);
            stroke-width: 12px;
        }}

        .score-ring-fill {{
            fill: none;
            stroke: var(--primary);
            stroke-width: 12px;
            stroke-dasharray: 439.8;
            stroke-dashoffset: {439.8 * (1 - score)};
            stroke-linecap: round;
            filter: drop-shadow(0 0 8px var(--primary-glow));
            transition: stroke-dashoffset 1s ease-out;
        }}

        .score-value-text {{
            position: absolute;
            font-family: 'Outfit', sans-serif;
            font-size: 2.5rem;
            font-weight: 700;
            color: var(--text-color);
            transform: translateY(54px);
        }}

        .score-label {{
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            margin-top: 1rem;
            font-size: 1.125rem;
            letter-spacing: 0.05em;
        }}

        .score-meta {{
            color: var(--text-muted);
            font-size: 0.8125rem;
            margin-top: 0.25rem;
        }}

        /* Key Metrics Cards */
        .metrics-cards-row {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .metric-card {{
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            padding: 1.25rem;
            backdrop-filter: blur(12px);
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }}

        .metric-card .label {{
            color: var(--text-muted);
            font-size: 0.8125rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .metric-card .value {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.75rem;
            font-weight: 600;
            color: var(--text-color);
        }}

        /* Category Card List */
        .categories-list {{
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }}

        .category-card {{
            background: rgba(255, 255, 255, 0.015);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            padding: 1.25rem;
            transition: var(--transition);
        }}

        .category-card:hover {{
            border-color: rgba(255, 255, 255, 0.15);
            transform: translateX(4px);
        }}

        .category-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.75rem;
        }}

        .category-title {{
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            font-size: 0.95rem;
        }}

        .category-meta {{
            font-size: 0.75rem;
            color: var(--text-muted);
        }}

        .progress-bar-container {{
            background: rgba(255, 255, 255, 0.05);
            height: 6px;
            border-radius: 999px;
            overflow: hidden;
            margin-bottom: 0.5rem;
        }}

        .progress-bar {{
            height: 100%;
            border-radius: 999px;
            background: var(--primary);
            box-shadow: 0 0 6px var(--primary-glow);
        }}

        .category-card.pass .progress-bar {{
            background: var(--success);
            box-shadow: 0 0 6px rgba(16, 185, 129, 0.4);
        }}

        .category-card.fail .progress-bar {{
            background: var(--critical);
            box-shadow: 0 0 6px rgba(239, 68, 68, 0.4);
        }}

        .category-score-value {{
            font-size: 0.8125rem;
            font-weight: 600;
            text-align: right;
            margin-bottom: 0.5rem;
        }}

        .category-details {{
            font-size: 0.75rem;
            color: var(--text-muted);
            list-style: none;
            padding-left: 0.25rem;
        }}

        .category-details li {{
            margin-top: 0.25rem;
            position: relative;
            padding-left: 0.75rem;
        }}

        .category-details li::before {{
            content: '•';
            position: absolute;
            left: 0;
            color: var(--primary);
        }}

        /* Infrastructure list */
        .infra-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2rem;
        }}

        .infra-card {{
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            padding: 1.25rem;
            backdrop-filter: blur(12px);
            transition: var(--transition);
        }}

        .infra-card:hover {{
            transform: translateY(-4px);
        }}

        .infra-card.infra-up {{
            border-color: rgba(16, 185, 129, 0.3);
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.02) 0%, rgba(255,255,255,0.02) 100%);
        }}

        .infra-card.infra-down {{
            border-color: rgba(239, 68, 68, 0.3);
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.02) 0%, rgba(255,255,255,0.02) 100%);
        }}

        .infra-service {{
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            font-size: 0.95rem;
            margin-bottom: 0.25rem;
        }}

        .infra-status {{
            font-size: 0.8125rem;
            font-weight: 500;
            margin-bottom: 0.5rem;
        }}

        .infra-latency {{
            font-family: monospace;
            font-size: 0.8125rem;
            color: var(--text-muted);
        }}

        .infra-error {{
            font-size: 0.75rem;
            color: var(--critical);
            margin-top: 0.5rem;
            word-break: break-all;
        }}

        /* Controls / Filter panel */
        .controls-panel {{
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            padding: 1.25rem;
            backdrop-filter: blur(12px);
            margin-bottom: 1.5rem;
            display: flex;
            gap: 1.25rem;
            flex-wrap: wrap;
            align-items: center;
        }}

        .search-box {{
            flex: 1;
            min-width: 240px;
            position: relative;
        }}

        .search-box input {{
            width: 100%;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--panel-border);
            border-radius: 8px;
            padding: 0.625rem 1rem 0.625rem 2.25rem;
            color: var(--text-color);
            font-family: inherit;
            transition: var(--transition);
        }}

        .search-box input:focus {{
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 10px var(--primary-glow);
        }}

        .search-box::before {{
            content: '🔍';
            position: absolute;
            left: 0.75rem;
            top: 50%;
            transform: translateY(-50%);
            font-size: 0.875rem;
            opacity: 0.5;
        }}

        .filter-select {{
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--panel-border);
            border-radius: 8px;
            padding: 0.625rem 1.5rem 0.625rem 1rem;
            color: var(--text-color);
            font-family: inherit;
            cursor: pointer;
            transition: var(--transition);
            min-width: 160px;
        }}

        .filter-select:focus {{
            outline: none;
            border-color: var(--primary);
        }}

        /* Test Explorer List */
        .test-list {{
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }}

        .test-card {{
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            backdrop-filter: blur(12px);
            overflow: hidden;
            transition: var(--transition);
        }}

        .test-card:hover {{
            border-color: rgba(255, 255, 255, 0.15);
        }}

        .test-card.row-pass {{
            border-left: 4px solid var(--success);
        }}

        .test-card.row-fail {{
            border-left: 4px solid var(--critical);
        }}

        .test-card-summary {{
            padding: 1.25rem;
            cursor: pointer;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }}

        .test-meta {{
            display: flex;
            gap: 0.75rem;
            align-items: center;
            flex-wrap: wrap;
        }}

        .badge {{
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            text-transform: uppercase;
        }}

        .badge.status-pass {{
            background: rgba(16, 185, 129, 0.1);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }}

        .badge.status-fail {{
            background: rgba(239, 68, 68, 0.1);
            color: var(--critical);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }}

        .badge.variant-complex {{
            background: rgba(168, 85, 247, 0.1);
            color: #c084fc;
            border: 1px solid rgba(168, 85, 247, 0.2);
        }}

        .badge.variant-hinglish {{
            background: rgba(59, 130, 246, 0.1);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.2);
        }}

        .badge.variant-adversarial {{
            background: rgba(245, 158, 11, 0.1);
            color: var(--warning);
            border: 1px solid rgba(245, 158, 11, 0.2);
        }}

        .test-category-badge {{
            font-family: monospace;
            font-size: 0.8125rem;
            color: var(--text-muted);
        }}

        .test-latency {{
            font-family: monospace;
            font-size: 0.8125rem;
            color: var(--text-muted);
            margin-left: auto;
        }}

        .test-query-summary {{
            font-family: 'Outfit', sans-serif;
            font-weight: 500;
            font-size: 1.05rem;
            color: var(--text-color);
        }}

        .test-card-details {{
            display: none;
            padding: 0 1.25rem 1.25rem 1.25rem;
            border-top: 1px solid var(--panel-border);
            background: rgba(0,0,0,0.15);
            animation: slideDown 0.3s ease-out;
        }}

        .original-query {{
            font-style: italic;
            color: var(--text-muted);
            margin-top: 1rem;
            font-size: 0.875rem;
            padding-left: 0.5rem;
            border-left: 2px solid var(--panel-border);
        }}

        .fail-reason-box {{
            background: rgba(239, 68, 68, 0.08);
            border: 1px solid rgba(239, 68, 68, 0.2);
            padding: 0.75rem 1rem;
            border-radius: 8px;
            margin-top: 1rem;
            color: #fca5a5;
            font-size: 0.875rem;
            font-weight: 500;
        }}

        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 1rem;
            margin-top: 1rem;
            margin-bottom: 1rem;
        }}

        .metrics-grid .metric-item {{
            background: rgba(255,255,255,0.02);
            border: 1px solid var(--panel-border);
            padding: 0.5rem;
            border-radius: 6px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}

        .metrics-grid .m-label {{
            font-size: 0.6875rem;
            color: var(--text-muted);
            text-transform: uppercase;
        }}

        .metrics-grid .m-val {{
            font-family: monospace;
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text-color);
        }}

        .response-box {{
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--panel-border);
            padding: 1rem;
            border-radius: 8px;
            margin-top: 0.75rem;
        }}

        .response-box strong {{
            font-size: 0.8125rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            display: block;
            margin-bottom: 0.5rem;
        }}

        .response-box p {{
            white-space: pre-wrap;
            font-size: 0.9375rem;
            color: #cbd5e1;
        }}

        .citations-container {{
            margin-top: 1rem;
            font-size: 0.8125rem;
            color: var(--text-muted);
        }}

        .citations-container strong {{
            display: block;
            margin-bottom: 0.25rem;
        }}

        .citations-container ul {{
            padding-left: 1.25rem;
        }}

        .timings-container {{
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
            margin-top: 1rem;
        }}

        .timing-chip {{
            background: rgba(99, 102, 241, 0.08);
            border: 1px solid rgba(99, 102, 241, 0.15);
            color: #a5b4fc;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.75rem;
        }}

        .debug-details {{
            margin-top: 1rem;
            font-family: monospace;
            font-size: 0.75rem;
            color: var(--text-muted);
            border-top: 1px dashed rgba(255,255,255,0.05);
            padding-top: 0.75rem;
        }}

        /* Latency Panel */
        .latency-panel {{
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 16px;
            padding: 1.5rem;
            backdrop-filter: blur(12px);
            text-align: center;
        }}

        /* Trace link */
        .trace-info {{
            margin-top: 0.75rem;
            font-family: monospace;
            font-size: 0.8125rem;
        }}
        .trace-link {{
            color: var(--primary);
            text-decoration: none;
        }}
        .trace-link:hover {{
            text-decoration: underline;
        }}

        /* Error stack */
        .error-stack-box {{
            background: rgba(239, 68, 68, 0.06);
            border: 1px solid rgba(239, 68, 68, 0.2);
            border-radius: 8px;
            padding: 0.75rem 1rem;
            margin-top: 1rem;
        }}
        .error-stack-box pre {{
            white-space: pre-wrap;
            font-size: 0.8125rem;
            color: #fca5a5;
            margin-top: 0.5rem;
        }}

        /* Docker log cards */
        .docker-log-card {{
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            margin-bottom: 1rem;
            overflow: hidden;
        }}
        .docker-log-header {{
            padding: 1rem 1.25rem;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--panel-border);
        }}
        .docker-log-service {{
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
        }}
        .docker-log-toggle {{
            color: var(--text-muted);
            font-size: 0.75rem;
        }}
        .docker-log-body {{
            display: none;
            padding: 1rem;
            background: rgba(0,0,0,0.3);
        }}
        .docker-log-body pre {{
            white-space: pre-wrap;
            font-family: monospace;
            font-size: 0.75rem;
            color: #94a3b8;
            line-height: 1.4;
            max-height: 400px;
            overflow-y: auto;
        }}

        /* Native Evaluator styles */
        .native-eval-section {{
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 16px;
            padding: 2rem;
            backdrop-filter: blur(12px);
            margin-bottom: 2rem;
        }}

        .section-title {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.5rem;
            margin-bottom: 1.5rem;
            color: var(--text-color);
        }}

        .native-summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2rem;
        }}

        .native-summary-card {{
            background: rgba(0,0,0,0.25);
            border: 1px solid var(--panel-border);
            padding: 1.25rem;
            border-radius: 12px;
            text-align: center;
        }}

        .native-summary-card .n-val {{
            font-family: 'Outfit', sans-serif;
            font-size: 2rem;
            font-weight: 700;
            color: var(--primary);
            margin-bottom: 0.25rem;
        }}

        .native-summary-card .n-lbl {{
            color: var(--text-muted);
            font-size: 0.8125rem;
        }}

        .native-list {{
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }}

        .native-eval-card {{
            background: rgba(255,255,255,0.015);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            padding: 1.25rem;
        }}

        .native-query {{
            font-family: 'Outfit', sans-serif;
            font-size: 1rem;
            font-weight: 500;
            margin-bottom: 0.5rem;
        }}

        .native-meta {{
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-bottom: 0.75rem;
        }}

        .native-scores {{
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
        }}

        .native-score-chip {{
            background: rgba(255,255,255,0.03);
            border: 1px solid var(--panel-border);
            padding: 0.375rem 0.75rem;
            border-radius: 6px;
            font-size: 0.8125rem;
            font-family: monospace;
        }}

        .empty-state {{
            background: var(--panel-bg);
            border: 1px dashed var(--panel-border);
            border-radius: 12px;
            padding: 3rem;
            text-align: center;
            color: var(--text-muted);
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(8px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        @keyframes slideDown {{
            from {{ opacity: 0; height: 0; padding-top: 0; padding-bottom: 0; }}
            to {{ opacity: 1; height: auto; }}
        }}

        /* Responsive */
        @media (max-width: 992px) {{
            .dashboard-grid {{
                grid-template-columns: 1fr;
            }}
            .metrics-cards-row {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}

        @media (max-width: 576px) {{
            body {{
                padding: 1rem;
            }}
            .metrics-cards-row {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <header>
        <div class="brand">
            <h1>AskMukthiGuru</h1>
            <div class="meta">PRODUCTION READINESS INSIGHTS</div>
        </div>
        <div class="run-meta-pills">
            <div class="pill">Run ID: {run_id[:8]}</div>
            <div class="pill">Backend: {backend_url}</div>
            <div class="pill">Generated: {formatted_time}</div>
            <div class="pill verdict-{verdict.lower()}">Verdict: {verdict}</div>
        </div>
    </header>

    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab(event, 'orchestrator-tab')">Orchestration & API Suite</button>
        <button class="tab-btn" onclick="switchTab(event, 'comprehensive-tab')">5-Tier Comprehensive</button>
        <button class="tab-btn" onclick="switchTab(event, 'native-ragas-tab')">Native RAGAS Evals</button>
        <button class="tab-btn" onclick="switchTab(event, 'system-infra-tab')">System & Infra Health</button>
        <button class="tab-btn" onclick="switchTab(event, 'docker-logs-tab')">🐳 Docker Logs</button>
    </div>

    <!-- Orchestrator Tab -->
    <div id="orchestrator-tab" class="tab-content active">
        <div class="metrics-cards-row">
            <div class="metric-card">
                <span class="label">Readiness Score</span>
                <span class="value" style="color: var(--primary)">{score:.1%}</span>
            </div>
            <div class="metric-card">
                <span class="label">Pass Rate</span>
                <span class="value" style="color: var(--success)">{pass_rate:.1%}</span>
            </div>
            <div class="metric-card">
                <span class="label">Avg Latency</span>
                <span class="value">{avg_latency:.0f} ms</span>
            </div>
            <div class="metric-card">
                <span class="label">Executed / Failed</span>
                <span class="value">{passed_tests} / {failed_tests}</span>
            </div>
        </div>

        <div class="dashboard-grid">
            <!-- Sidebar -->
            <div class="sidebar">
                <div class="score-panel">
                    <div style="position: relative; width: 160px; height: 160px;">
                        <span class="score-value-text">{score:.0%}</span>
                        <svg class="score-ring-svg">
                            <circle class="score-ring-bg" cx="80" cy="80" r="70"></circle>
                            <circle class="score-ring-fill" cx="80" cy="80" r="70"></circle>
                        </svg>
                    </div>
                    <div class="score-label">Readiness Index</div>
                    <div class="score-meta">Required score to release is 95%</div>
                </div>

                <div class="latency-panel">
                    <h3 style="font-family: 'Outfit'; font-size: 1.1rem; margin-bottom: 0.75rem;">⏱ Latency Distribution</h3>
                    <svg width="{chart_svg_width}" height="{bar_height + 30}" viewBox="0 0 {chart_svg_width} {bar_height + 30}">
                        {bars_svg}
                    </svg>
                </div>

                <div class="categories-list">
                    <h3 style="font-family: 'Outfit'; font-size: 1.1rem; margin-bottom: 0.5rem;">Category Indexes</h3>
                    {category_rows_html}
                </div>
            </div>

            <!-- Main Panel -->
            <div class="main-panel">
                <div class="controls-panel">
                    <div class="search-box">
                        <input type="text" id="searchInput" placeholder="Search queries, responses, intents..." oninput="filterTests()">
                    </div>
                    <select class="filter-select" id="categoryFilter" onchange="filterTests()">
                        <option value="ALL">All Categories</option>
                        {"".join(f'<option value="{c}">{c}</option>' for c in sorted(list(set(r.get("category") for r in results))))}
                    </select>
                    <select class="filter-select" id="statusFilter" onchange="filterTests()">
                        <option value="ALL">All Statuses</option>
                        <option value="PASS">Passed Only</option>
                        <option value="FAIL">Failed Only</option>
                    </select>
                    <select class="filter-select" id="variantFilter" onchange="filterTests()">
                        <option value="ALL">All Variants</option>
                        <option value="original">Original Only</option>
                        <option value="complex">Complex Only</option>
                        <option value="hinglish">Hinglish Only</option>
                        <option value="adversarial">Adversarial Only</option>
                    </select>
                </div>

                <div class="test-list" id="testList">
                    {results_rows_html}
                </div>
            </div>
        </div>
    </div>

    <!-- Native Ragas Tab -->
    <div id="native-ragas-tab" class="tab-content">
        {native_eval_html}
    </div>

    <!-- Comprehensive Tab -->
    <div id="comprehensive-tab" class="tab-content">
        <h2 class="section-title">📋 5-Tier Comprehensive Benchmark</h2>
        <p style="color: var(--text-muted); margin-bottom: 1.5rem;">Tier 1: Simple Factual · Tier 2: Complex/Reasoning · Tier 3: Distress · Tier 4: Guardrail · Tier 5: Edge</p>
        {comp_html if comp_html else '<div class="empty-state">⚠️ No comprehensive benchmark data found. Run comprehensive_benchmark.py first.</div>'}
    </div>

    <!-- Docker Logs Tab -->
    <div id="docker-logs-tab" class="tab-content">
        <h2 class="section-title">🐳 Docker Container Logs</h2>
        <p style="color: var(--text-muted); margin-bottom: 1.5rem;">Last 200 lines per service, collected at report generation time.</p>
        {docker_logs_html if docker_logs_html else '<div class="empty-state">⚠️ No docker logs collected. Ensure Docker is running.</div>'}
    </div>

    <!-- System & Infra Health Tab -->
    <div id="system-infra-tab" class="tab-content">
        <h2 class="section-title">🖥️ Component Health & Connection Latencies</h2>
        <div class="infra-grid">
            {infra_cards_html}
        </div>
        
        <div class="score-panel" style="text-align: left; align-items: flex-start; max-width: 800px;">
            <h3 style="font-family: 'Outfit'; font-size: 1.25rem; margin-bottom: 1rem; color: var(--primary);">Spiritual RAG Pipeline Architecture</h3>
            <p style="color: var(--text-muted); margin-bottom: 1.5rem;">
                AskMukthiGuru processes user queries through a multi-tiered, resilient semantic architecture:
            </p>
            <div style="display: flex; flex-direction: column; gap: 0.75rem; width: 100%;">
                <div style="display: flex; gap: 1rem; align-items: center; background: rgba(255,255,255,0.02); padding: 0.75rem; border-radius: 8px; border: 1px solid var(--panel-border);">
                    <span style="font-size: 1.5rem;">🛡️</span>
                    <div>
                        <strong>Tier 1: Input Guardrails & Routing</strong>
                        <div style="font-size: 0.8125rem; color: var(--text-muted);">Lightweight Guardrails inspect input for jailbreaks or off-topic prompts. Enforces spiritual boundaries.</div>
                    </div>
                </div>
                <div style="display: flex; gap: 1rem; align-items: center; background: rgba(255,255,255,0.02); padding: 0.75rem; border-radius: 8px; border: 1px solid var(--panel-border);">
                    <span style="font-size: 1.5rem;">⚡</span>
                    <div>
                        <strong>Tier 2: Semantic Cache Verification</strong>
                        <div style="font-size: 0.8125rem; color: var(--text-muted);">Redis-backed GPTCache tests local semantic similarity. Returns cached wisdom under 10ms on hit.</div>
                    </div>
                </div>
                <div style="display: flex; gap: 1rem; align-items: center; background: rgba(255,255,255,0.02); padding: 0.75rem; border-radius: 8px; border: 1px solid var(--panel-border);">
                    <span style="font-size: 1.5rem;">🧬</span>
                    <div>
                        <strong>Tier 3: Hybrid Retrieval (Qdrant & Neo4j)</strong>
                        <div style="font-size: 0.8125rem; color: var(--text-muted);">Parallel dense vector lookup in Qdrant combined with structural entity retrieval from Neo4j Knowledge Graph.</div>
                    </div>
                </div>
                <div style="display: flex; gap: 1rem; align-items: center; background: rgba(255,255,255,0.02); padding: 0.75rem; border-radius: 8px; border: 1px solid var(--panel-border);">
                    <span style="font-size: 1.5rem;">🧠</span>
                    <div>
                        <strong>Tier 4: Context Reranking & LLM Reasoning</strong>
                        <div style="font-size: 0.8125rem; color: var(--text-muted);">Cross-encoder models compress and rank documents. Prompt routes to Sarvam 30B for final reasoning.</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        function switchTab(evt, tabId) {{
            const contents = document.querySelectorAll('.tab-content');
            contents.forEach(c => c.classList.remove('active'));
            
            const buttons = document.querySelectorAll('.tab-btn');
            buttons.forEach(b => b.classList.remove('active'));
            
            document.getElementById(tabId).classList.add('active');
            evt.currentTarget.classList.add('active');
        }}

        function toggleDetails(summaryEl) {{
            const detailsEl = summaryEl.nextElementSibling;
            const isVisible = window.getComputedStyle(detailsEl).display !== 'none';
            detailsEl.style.display = isVisible ? 'none' : 'block';
        }}

        function filterTests() {{
            const searchQuery = document.getElementById('searchInput').value.toLowerCase();
            const categoryFilter = document.getElementById('categoryFilter').value;
            const statusFilter = document.getElementById('statusFilter').value;
            const variantFilter = document.getElementById('variantFilter').value;
            
            const cards = document.querySelectorAll('#testList .test-card');
            
            cards.forEach(card => {{
                const searchData = card.getAttribute('data-search') || '';
                const cardCategory = card.getAttribute('data-category') || '';
                const cardStatus = card.getAttribute('data-status') || '';
                const cardVariant = card.getAttribute('data-variant') || 'original';
                
                const matchesSearch = !searchQuery || searchData.includes(searchQuery);
                const matchesCategory = categoryFilter === 'ALL' || cardCategory === categoryFilter;
                const matchesStatus = statusFilter === 'ALL' || cardStatus === statusFilter;
                const matchesVariant = variantFilter === 'ALL' || cardVariant === variantFilter;
                
                if (matchesSearch && matchesCategory && matchesStatus && matchesVariant) {{
                    card.style.display = 'block';
                }} else {{
                    card.style.display = 'none';
                }}
            }});
        }}
    </script>
</body>
</html>
"""
    return html

def main():
    print("🚀 Generating dashboard.html...")
    ruthless, native, comprehensive = load_reports()
    
    if not ruthless and not native and not comprehensive:
        print("⚠️ No data reports found. Cannot generate dashboard.")
        sys.exit(1)
    
    print("  📡 Collecting docker logs...")
    docker_logs = collect_docker_logs()
        
    html = build_html(ruthless, native, comprehensive, docker_logs)
    
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(DASHBOARD_PATH, "w") as f:
        f.write(html)
        
    print(f"✨ Dashboard generated successfully: {DASHBOARD_PATH}")

if __name__ == "__main__":
    main()
