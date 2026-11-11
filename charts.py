
import os
import re
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import pandas as pd
import numpy as np


# Folder where graph images will be stored
GRAPH_FOLDER = os.path.join("static", "graphs")
os.makedirs(GRAPH_FOLDER, exist_ok=True)

# Colors matching the frontend dashboard category legend
CAT_COLORS = [
    "#6366f1", "#8b5cf6", "#06b6d4", "#10b981", "#f59e0b",
    "#ef4444", "#f97316", "#ec4899", "#14b8a6", "#84cc16"
]


# Common graph design
def save_graph(fig, filename):
    path = os.path.join(GRAPH_FOLDER, filename)
    fig.tight_layout()
    fig.savefig(path, dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    return "/" + path.replace("\\", "/")


def get_value(item, possible_keys, default=None):
    for key in possible_keys:
        if key in item and item[key] is not None:
            return item[key]
    return default


# 1. Monthly / Daily Spending Graph
def generate_monthly_chart(data, daily_data=None, user_id=None):
    filename = f"monthly_u{user_id}.png" if user_id is not None else "monthly.png"
    month_dict = {}

    for item in data or []:
        raw_month = get_value(item, ["month", "date", "label", "period"], None)
        raw_val = get_value(item, ["amount", "total", "spend", "value"], 0)
        try:
            val = float(raw_val)
        except (ValueError, TypeError):
            val = 0.0

        if not raw_month or val <= 0:
            continue

        s = str(raw_month).strip()
        dt = pd.to_datetime(s, errors="coerce")
        if pd.isna(dt):
            m = re.search(r"(\d{4})[-/.](\d{1,2})", s)
            if m:
                dt = pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)
            else:
                m2 = re.search(r"(\d{1,2})[-/.](\d{4})", s)
                if m2:
                    dt = pd.Timestamp(year=int(m2.group(2)), month=int(m2.group(1)), day=1)

        if not pd.isna(dt):
            key = dt.to_period("M")
            month_dict[key] = month_dict.get(key, 0.0) + val
        else:
            key = s[:7]
            month_dict[key] = month_dict.get(key, 0.0) + val

    fig, ax = plt.subplots(figsize=(8, 3.6), facecolor="#151f30")
    ax.set_facecolor("#151f30")

    if not month_dict and not daily_data:
        ax.text(0.5, 0.5, "No monthly spending data available",
                ha="center", va="center", color="#94a3b8", fontsize=11)
        ax.set_title("Monthly Spending Trend", color="#e2e8f0", fontsize=12, fontweight="bold", pad=12)
        ax.axis("off")
        return save_graph(fig, filename)

    # If uploaded statement contains only one month of data:
    # Display a meaningful daily spending trend for that month instead of an awkward single bar
    if len(month_dict) == 1 and daily_data:
        single_period = list(month_dict.keys())[0]
        if not isinstance(single_period, pd.Period):
            try:
                single_period = pd.Period(str(single_period)[:7], freq="M")
            except Exception:
                try:
                    single_period = pd.to_datetime(str(single_period)).to_period("M")
                except Exception:
                    pass
        if hasattr(single_period, "strftime"):
            month_abbr = single_period.strftime("%b")
            days_in_month = getattr(single_period, "days_in_month", 30)
        else:
            month_abbr = str(single_period)[:3]
            days_in_month = 30

        day_dict = {}
        for item in daily_data or []:
            d_val = get_value(item, ["date", "day", "label"], None)
            amt = float(get_value(item, ["total", "amount", "spend", "value"], 0))
            if d_val:
                dt_d = pd.to_datetime(d_val, errors="coerce")
                if not pd.isna(dt_d):
                    day_dict[dt_d.day] = day_dict.get(dt_d.day, 0.0) + amt

        all_days = list(range(1, days_in_month + 1))
        daily_values = [day_dict.get(d, 0.0) for d in all_days]

        # Draw daily spending trend
        bars = ax.bar(all_days, daily_values, color="#6366f1", width=0.6, edgecolor="#818cf8", linewidth=0.8, alpha=0.85, zorder=3)
        ax.plot(all_days, daily_values, color="#38bdf8", linewidth=1.8, marker="o", markersize=3.5, zorder=4)

        ax.set_title(f"Daily Spending Trend – {month_abbr} (Single Month Statement)", color="#e2e8f0", fontsize=11, fontweight="bold", pad=12)
        ax.set_xlabel(f"Date ({month_abbr})", color="#94a3b8", fontsize=9)
        ax.set_ylabel("Amount (₹)", color="#94a3b8", fontsize=9)

        # Display clean, non-overlapping date labels: 01 Sep, 05 Sep, 10 Sep... without year
        tick_days = [1, 5, 10, 15, 20, 25]
        if days_in_month not in tick_days:
            tick_days.append(days_in_month)
        tick_days = sorted(tick_days)
        tick_labels = [f"{d:02d} {month_abbr}" for d in tick_days]

        ax.set_xticks(tick_days)
        ax.set_xticklabels(tick_labels, rotation=15, ha="right", color="#94a3b8", fontsize=8.5)
        ax.tick_params(colors="#94a3b8", labelsize=8)
        ax.grid(axis="y", color="#1e2d45", linestyle="--", alpha=0.7, zorder=0)

        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        for spine in ["left", "bottom"]:
            ax.spines[spine].set_color("#1e2d45")

        max_day = max(daily_values) if daily_values else 1.0
        ax.set_ylim(0, max_day * 1.18 if max_day > 0 else 100)

        # Highlight highest spending days with spacing to avoid overlapping text
        sorted_days = sorted([(amt, day) for day, amt in day_dict.items() if amt > 0], reverse=True)
        selected_days = []
        for amt, day in sorted_days:
            if not any(abs(day - s_day) < 2 for _, s_day in selected_days):
                selected_days.append((amt, day))
            if len(selected_days) >= 4:
                break

        for amt, day in selected_days:
            ax.text(
                day,
                amt + (max_day * 0.025),
                f"₹{amt:,.0f}",
                ha="center",
                va="bottom",
                color="#e2e8f0",
                fontsize=7.5,
                fontweight="bold",
                zorder=5
            )

        return save_graph(fig, filename)

    # If only one month without daily details, show a well-proportioned bar with clear single-month note
    if len(month_dict) == 1:
        single_period = list(month_dict.keys())[0]
        if not isinstance(single_period, pd.Period):
            try:
                single_period = pd.Period(str(single_period)[:7], freq="M")
            except Exception:
                try:
                    single_period = pd.to_datetime(str(single_period)).to_period("M")
                except Exception:
                    pass
        month_label = single_period.strftime("%b %Y") if hasattr(single_period, "strftime") else str(single_period)
        val = sum(month_dict.values())

        ax.bar([0], [val], color="#6366f1", width=0.35, edgecolor="#818cf8", linewidth=1.2, zorder=3)
        ax.set_xlim(-1.2, 1.2)
        ax.set_xticks([0])
        ax.set_xticklabels([month_label], color="#94a3b8", fontsize=10, fontweight="bold")
        ax.tick_params(axis="y", colors="#94a3b8", labelsize=9)
        ax.set_title(f"Spending Overview – {month_label} (Single Month Statement)", color="#e2e8f0", fontsize=11, fontweight="bold", pad=12)
        ax.set_ylabel("Amount (₹)", color="#94a3b8", fontsize=10)
        ax.grid(axis="y", color="#1e2d45", linestyle="--", alpha=0.7, zorder=0)

        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        for spine in ["left", "bottom"]:
            ax.spines[spine].set_color("#1e2d45")

        ax.set_ylim(0, val * 1.25)
        ax.text(0, val + (val * 0.03), f"₹{val:,.0f}", ha="center", va="bottom", color="#e2e8f0", fontsize=10, fontweight="bold")
        ax.text(0, val * 0.5, "Only 1 month of statement data available\nUpload statements spanning 2+ months for month-over-month trend",
                ha="center", va="center", color="#94a3b8", fontsize=8.5, style="italic",
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#1e2d45", edgecolor="#334155", alpha=0.85))

        return save_graph(fig, filename)

    # Multi-month statement: display ONLY months that actually have transaction data.
    # Dynamically generated from actual transaction dates and sorted chronologically.
    # Do NOT create a fixed January–December list and do NOT fill missing months with zero values.
    sorted_keys = sorted(month_dict.keys())
    ordered = []
    for k in sorted_keys:
        val = month_dict[k]
        if val <= 0:
            continue
        if isinstance(k, pd.Period):
            lbl = k.strftime("%b")
        else:
            try:
                lbl = pd.to_datetime(str(k)).strftime("%b")
            except Exception:
                lbl = str(k)
        ordered.append((lbl, val))

    labels = [x[0] for x in ordered]
    values = [x[1] for x in ordered]

    # Bar chart with FinLens dark styling
    bars = ax.bar(
        range(len(labels)),
        values,
        color="#6366f1",
        width=0.52,
        edgecolor="#818cf8",
        linewidth=1,
        zorder=3
    )

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=0 if len(labels) <= 7 else 15, ha="center" if len(labels) <= 7 else "right", color="#94a3b8", fontsize=9)
    ax.tick_params(axis="y", colors="#94a3b8", labelsize=9)
    ax.set_title("Monthly Spending Trend", color="#e2e8f0", fontsize=12, fontweight="bold", pad=14)
    ax.set_ylabel("Amount (₹)", color="#94a3b8", fontsize=10)
    ax.grid(axis="y", color="#1e2d45", linestyle="--", alpha=0.7, zorder=0)

    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color("#1e2d45")

    max_val = max(values) if values else 1.0
    y_margin = max_val * 0.16 if max_val > 0 else 100
    ax.set_ylim(0, max_val + y_margin)

    # Display spending amounts above each bar
    for bar, val in zip(bars, values):
        height = bar.get_height()
        if height > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height + (max_val * 0.02),
                f"₹{height:,.0f}",
                ha="center",
                va="bottom",
                color="#e2e8f0",
                fontsize=8.5,
                fontweight="bold",
                zorder=4
            )
        else:
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                max_val * 0.015,
                "₹0",
                ha="center",
                va="bottom",
                color="#64748b",
                fontsize=7.5,
                zorder=4
            )

    return save_graph(fig, filename)


# 2. Spending by Category Graph (Donut)
def generate_category_chart(data, user_id=None):
    filename = f"category_u{user_id}.png" if user_id is not None else "category.png"
    labels = []
    values = []

    for item in data or []:
        cat = str(get_value(item, ["category", "name", "label"], "Others"))
        val = float(get_value(item, ["total", "amount", "spend", "value"], 0))
        if cat.lower() == "other":
            cat = "Others"
        if val > 0:
            labels.append(cat)
            values.append(val)

    fig, ax = plt.subplots(figsize=(6, 3.5), facecolor="#151f30")
    ax.set_facecolor("#151f30")

    total_spend = sum(values)

    if values and total_spend > 0:
        # Match colors with frontend category legend exactly
        colors = [CAT_COLORS[i % len(CAT_COLORS)] for i in range(len(values))]

        wedges, texts, autotexts = ax.pie(
            values,
            labels=None,
            autopct="%1.1f%%",
            pctdistance=0.76,
            startangle=90,
            colors=colors,
            wedgeprops=dict(width=0.45, edgecolor="#151f30", linewidth=2)
        )

        for autotext in autotexts:
            autotext.set_color("#ffffff")
            autotext.set_fontsize(8.5)
            autotext.set_weight("bold")

        # Display total in center of donut
        ax.text(
            0, 0,
            f"Total\n₹{total_spend:,.0f}",
            ha="center",
            va="center",
            color="#e2e8f0",
            fontsize=10.5,
            fontweight="bold"
        )
    else:
        ax.text(
            0.5, 0.5,
            "No category data available",
            ha="center",
            va="center",
            color="#94a3b8",
            fontsize=11
        )
        ax.axis("off")

    ax.set_title("Spending by Category", color="#e2e8f0", fontsize=12, fontweight="bold", pad=12)

    return save_graph(fig, filename)


# 3. Rolling 30-Day Spending Graph
def generate_rolling_chart(data, user_id=None):
    filename = f"rolling_u{user_id}.png" if user_id is not None else "rolling.png"
    formatted_labels = []
    values = []

    for item in data or []:
        raw_d = get_value(item, ["date", "day", "label"], "")
        val = float(get_value(item, ["amount", "total", "spend", "value"], 0))
        dt = pd.to_datetime(raw_d, errors="coerce")
        if not pd.isna(dt):
            # Display only month and date, NO year (e.g. "01 Sep", "15 Sep")
            formatted_labels.append(f"{dt.day:02d} {dt.strftime('%b')}")
        else:
            formatted_labels.append(str(raw_d)[:10])
        values.append(val)

    fig, ax = plt.subplots(figsize=(8, 3.2), facecolor="#151f30")
    ax.set_facecolor("#151f30")

    n = len(values)
    if n > 0:
        ax.plot(range(n), values, color="#38bdf8", linewidth=1.8, marker="o", markersize=3.5, zorder=3)
        ax.fill_between(range(n), values, color="#38bdf8", alpha=0.12, zorder=2)

        # Select clean, non-overlapping tick marks across the range
        if n <= 8:
            tick_indices = list(range(n))
        else:
            tick_indices = list(np.linspace(0, n - 1, num=min(7, n), dtype=int))
            if (n - 1) not in tick_indices:
                tick_indices[-1] = n - 1
            tick_indices = sorted(list(set(int(i) for i in tick_indices)))

        ax.set_xticks(tick_indices)
        ax.set_xticklabels([formatted_labels[i] for i in tick_indices], rotation=15, ha="right", color="#94a3b8", fontsize=8.5)
        max_v = max(values)
        ax.set_ylim(0, max_v * 1.15 if max_v > 0 else 100)
    else:
        ax.text(0.5, 0.5, "No rolling spending data available",
                ha="center", va="center", color="#94a3b8", fontsize=11)
        ax.axis("off")

    ax.set_title("Rolling 30-Day Spending", color="#e2e8f0", fontsize=11, fontweight="bold", pad=12)
    ax.set_ylabel("Amount (₹)", color="#94a3b8", fontsize=9)
    ax.tick_params(colors="#94a3b8", labelsize=8)
    ax.grid(axis="y", color="#1e2d45", linestyle="--", alpha=0.7, zorder=0)

    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color("#1e2d45")

    return save_graph(fig, filename)


# 4. Anomaly Detection Graph
def generate_anomaly_chart(data, user_id=None):
    filename = f"anomalies_u{user_id}.png" if user_id is not None else "anomalies.png"
    labels = []
    values = []

    for index, item in enumerate(data or []):
        labels.append(str(get_value(
            item, ["description", "merchant", "name"], f"Transaction {index + 1}"
        )))
        values.append(float(get_value(
            item, ["amount", "total", "spend", "value"], 0
        )))

    fig, ax = plt.subplots(figsize=(8, 3.5), facecolor="#151f30")
    ax.set_facecolor("#151f30")

    if values:
        bars = ax.bar(range(len(values)), values, color="#f59e0b", edgecolor="#fbbf24", width=0.55, linewidth=1, alpha=0.85, zorder=3)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=25, ha="right", color="#94a3b8", fontsize=8.5)
        max_v = max(values)
        ax.set_ylim(0, max_v * 1.18 if max_v > 0 else 100)
    else:
        ax.text(0.5, 0.5, "No anomalies detected",
                ha="center", va="center", color="#94a3b8", fontsize=11)
        ax.axis("off")

    ax.set_title("Anomaly Detection", color="#e2e8f0", fontsize=11, fontweight="bold", pad=12)
    ax.set_ylabel("Amount (₹)", color="#94a3b8", fontsize=9)
    ax.tick_params(colors="#94a3b8", labelsize=8)
    ax.grid(axis="y", color="#1e2d45", linestyle="--", alpha=0.7, zorder=0)

    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color("#1e2d45")

    return save_graph(fig, filename)


def generate_whatif_chart(months, keep, after, user_id=None):
    filename = f"whatif_u{user_id}.png" if user_id is not None else "whatif.png"
    fig, ax = plt.subplots(figsize=(8, 3.8), facecolor="#151f30")
    ax.set_facecolor("#151f30")

    keep_vals = [float(x) for x in (keep or [])]
    after_vals = [float(x) for x in (after or [])]
    max_val = max(keep_vals) if keep_vals else 0.0

    if not keep_vals or max_val == 0.0:
        ax.text(0.5, 0.55, "No active subscriptions detected",
                ha="center", va="center", color="#e2e8f0", fontsize=11, fontweight="bold")
        ax.text(0.5, 0.38, "Upload statements spanning 2+ months with recurring charges\nto simulate cancellation savings over time.",
                ha="center", va="center", color="#94a3b8", fontsize=9, multialignment="center")
        ax.set_title("Subscription Savings Projection (12 Months)", color="#e2e8f0", fontsize=11, fontweight="bold", pad=12)
        ax.axis("off")
        return save_graph(fig, filename)

    m = list(months)
    ax.plot(m, keep_vals, color="#ef4444", linewidth=2.0, marker="o", markersize=4, label="Current Spending (Keep All)", zorder=3)
    ax.plot(m, after_vals, color="#10b981", linewidth=2.0, marker="o", markersize=4, label="New Spending (After Cancellation)", zorder=4)

    # Shading the savings area between keep and after
    diff = [k - a for k, a in zip(keep_vals, after_vals)]
    total_saved_12m = diff[-1] if diff else 0.0
    if total_saved_12m > 0:
        ax.fill_between(m, after_vals, keep_vals, color="#10b981", alpha=0.18, label=f"Cumulative Savings (₹{total_saved_12m:,.0f})", zorder=2)

    ax.set_title("Subscription Savings Projection (12 Months)", color="#e2e8f0", fontsize=11, fontweight="bold", pad=12)
    ax.set_xlabel("Months Ahead", color="#94a3b8", fontsize=9)
    ax.set_ylabel("Cumulative Cost (₹)", color="#94a3b8", fontsize=9)
    ax.set_xticks(m)
    ax.tick_params(colors="#94a3b8", labelsize=8.5)
    ax.grid(axis="both", color="#1e2d45", linestyle="--", alpha=0.7, zorder=0)

    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color("#1e2d45")

    y_top = max_val * 1.15 if max_val > 0 else 100
    ax.set_ylim(0, y_top)

    ax.legend(facecolor="#1e2d45", edgecolor="#334155", labelcolor="#e2e8f0", fontsize=8.5, loc="upper left")

    return save_graph(fig, filename)