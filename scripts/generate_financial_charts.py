#!/usr/bin/env python3
"""Generate financial charts for the Business Plan."""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CHART_DIR = REPO_ROOT / "docs" / "external" / "pdf" / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)

# Brand colors
NAVY = '#1a3a5c'
BLUE = '#2a5a8c'
LIGHT_BLUE = '#4a8abf'
GREEN = '#2d8a4e'
RED = '#c0392b'
ORANGE = '#e67e22'
GRAY = '#95a5a6'
LIGHT_GRAY = '#ecf0f1'
GOLD = '#f39c12'

# Common style settings
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Helvetica Neue', 'Arial', 'sans-serif'],
    'font.size': 10,
    'axes.titlesize': 13,
    'axes.labelsize': 11,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'axes.grid': True,
    'grid.alpha': 0.3,
    'grid.color': '#cccccc',
})


def format_eur(x, _):
    """Format number as EUR K."""
    if abs(x) >= 1000:
        return f'EUR {x/1000:.1f}M'
    return f'EUR {x:.0f}K'


def chart_monthly_cashflow():
    """Monthly cash flow waterfall over 36 months."""
    months = np.arange(1, 37)

    # Monthly revenue (base case, ramping)
    monthly_revenue = np.zeros(36)
    # Y1: 8 customers acquired spread across months, avg ACV 120K -> 10K/mo per customer
    for m in range(36):
        if m < 3:
            customers = 0  # pilot period
        elif m < 6:
            customers = 1 + (m - 3)  # 1-3 customers
        elif m < 9:
            customers = 3 + (m - 6)  # 4-6 customers
        elif m < 12:
            customers = 6 + (m - 9)  # 7-8 customers
        elif m < 18:
            customers = 8 + int((m - 12) * 2.5)  # growing to ~23
        elif m < 24:
            customers = 23 + int((m - 18) * 3)  # growing to ~41
        else:
            customers = 41 + int((m - 24) * 3)  # growing toward 60

        avg_monthly_acv = 10 if m < 12 else 12.5 if m < 24 else 15  # K/mo per customer
        monthly_revenue[m] = customers * avg_monthly_acv

    # Monthly costs (ramping with hires)
    monthly_costs = np.zeros(36)
    # Personnel ramp (from hiring plan)
    personnel_monthly = np.array([
        # Y1: M1-12
        38, 49, 62, 88, 103, 114, 121, 121, 148, 158, 158, 175,
        # Y2: M13-24
        175, 182, 200, 206, 206, 221, 230, 241, 241, 241, 241, 241,
        # Y3: M25-36 (Series A hires: +8 people)
        260, 270, 280, 290, 300, 310, 320, 330, 340, 350, 350, 350,
    ])
    # Non-personnel costs
    non_personnel_monthly = np.array([
        # Y1
        35, 30, 35, 35, 40, 45, 50, 50, 55, 55, 55, 60,
        # Y2
        60, 60, 65, 65, 65, 70, 70, 70, 75, 75, 75, 75,
        # Y3
        80, 80, 85, 85, 85, 90, 90, 90, 95, 95, 95, 95,
    ])
    monthly_costs = personnel_monthly + non_personnel_monthly

    # Net cash flow
    net_monthly = monthly_revenue - monthly_costs

    # Cumulative cash position (starting with 5000K)
    cash_position = np.zeros(36)
    cash_position[0] = 5000 + net_monthly[0]
    for i in range(1, 36):
        cash_position[i] = cash_position[i-1] + net_monthly[i]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[1, 1])
    fig.suptitle('Monthly Cash Flow Analysis (36 Months)', fontsize=14, fontweight='bold', color=NAVY, y=0.98)

    # Top chart: Revenue vs Costs
    ax1.fill_between(months, monthly_revenue, alpha=0.3, color=GREEN, label='Revenue')
    ax1.fill_between(months, monthly_costs, alpha=0.3, color=RED, label='Costs')
    ax1.plot(months, monthly_revenue, color=GREEN, linewidth=2)
    ax1.plot(months, monthly_costs, color=RED, linewidth=2)
    ax1.axvline(x=12.5, color=GRAY, linestyle='--', alpha=0.5)
    ax1.axvline(x=24.5, color=GRAY, linestyle='--', alpha=0.5)
    ax1.text(6.5, max(monthly_costs) * 0.95, 'Year 1', ha='center', color=GRAY, fontsize=9)
    ax1.text(18.5, max(monthly_costs) * 0.95, 'Year 2', ha='center', color=GRAY, fontsize=9)
    ax1.text(30.5, max(monthly_costs) * 0.95, 'Year 3', ha='center', color=GRAY, fontsize=9)
    ax1.set_ylabel('EUR K / month')
    ax1.set_title('Monthly Revenue vs Operating Costs', fontsize=11, color=NAVY)
    ax1.legend(loc='upper left')
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:.0f}K'))

    # Find break-even month
    breakeven_month = None
    for i in range(len(net_monthly)):
        if net_monthly[i] > 0:
            breakeven_month = i + 1
            break

    if breakeven_month:
        ax1.axvline(x=breakeven_month, color=GOLD, linestyle='-', alpha=0.8, linewidth=2)
        ax1.annotate(f'Break-even\nMonth {breakeven_month}',
                    xy=(breakeven_month, monthly_revenue[breakeven_month-1]),
                    xytext=(breakeven_month + 3, monthly_revenue[breakeven_month-1] * 0.7),
                    arrowprops=dict(arrowstyle='->', color=GOLD),
                    fontsize=9, color=GOLD, fontweight='bold')

    # Bottom chart: Cash Position
    colors = [GREEN if c > 2000 else ORANGE if c > 1000 else RED for c in cash_position]
    ax2.fill_between(months, cash_position, alpha=0.2, color=BLUE)
    ax2.plot(months, cash_position, color=NAVY, linewidth=2.5)
    ax2.axhline(y=1000, color=RED, linestyle='--', alpha=0.5, label='Minimum safe reserve (EUR 1M)')
    ax2.axvline(x=12.5, color=GRAY, linestyle='--', alpha=0.5)
    ax2.axvline(x=24.5, color=GRAY, linestyle='--', alpha=0.5)
    ax2.set_xlabel('Month')
    ax2.set_ylabel('EUR K')
    ax2.set_title('Cumulative Cash Position (EUR 5M Starting)', fontsize=11, color=NAVY)
    ax2.legend(loc='upper right')
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x/1000:.1f}M' if x >= 1000 else f'{x:.0f}K'))

    # Add Series A annotation
    ax2.annotate('Series A\n(EUR 15-25M)',
                xy=(20, cash_position[19]),
                xytext=(24, cash_position[19] + 800),
                arrowprops=dict(arrowstyle='->', color=BLUE),
                fontsize=9, color=BLUE, fontweight='bold',
                ha='center')

    plt.tight_layout()
    plt.savefig(CHART_DIR / 'monthly_cashflow.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Generated: {CHART_DIR / 'monthly_cashflow.png'}")


def chart_headcount_growth():
    """Headcount growth by function over 24 months."""
    months = np.arange(0, 25)

    engineering = np.array([
        1, 2, 3, 4, 4, 4, 4, 5, 5, 5, 6, 6, 6,  # M0-12
        8, 8, 8, 9, 9, 9, 10, 10, 11, 11, 11, 12  # M13-24
    ])
    commercial = np.array([
        0, 0, 0, 0, 0, 2, 2, 3, 3, 3, 4, 4, 5,  # M0-12
        5, 6, 6, 6, 7, 7, 7, 8, 8, 8, 8, 8  # M13-24
    ])
    leadership = np.array([
        1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3,  # M0-12
        3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4  # M13-24
    ])
    operations = np.array([
        0, 0, 0, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2,  # M0-12
        2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2  # M13-24
    ])

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle('Headcount Growth by Function (24 Months)', fontsize=14, fontweight='bold', color=NAVY)

    ax.stackplot(months, engineering, commercial, leadership, operations,
                labels=['Engineering', 'Commercial (Sales/CS/Marketing)', 'Leadership (C-Suite)', 'Operations (G&A)'],
                colors=[BLUE, GREEN, NAVY, GRAY], alpha=0.8)

    total = engineering + commercial + leadership + operations
    ax.plot(months, total, color='black', linewidth=1.5, linestyle='--', alpha=0.5)

    # Annotate key milestones
    for m, label in [(1, 'CTO'), (4, 'CRO'), (9, 'CEO'), (15, 'CFO')]:
        ax.annotate(label, xy=(m, total[m]), xytext=(m, total[m] + 2),
                   fontsize=8, fontweight='bold', color=NAVY, ha='center',
                   arrowprops=dict(arrowstyle='->', color=NAVY, lw=0.8))

    ax.set_xlabel('Month')
    ax.set_ylabel('Number of Employees')
    ax.legend(loc='upper left', fontsize=9)
    ax.set_xlim(0, 24)
    ax.set_ylim(0, max(total) + 5)

    # Phase labels
    ax.axvspan(0, 6, alpha=0.05, color=BLUE)
    ax.axvspan(6, 12, alpha=0.05, color=GREEN)
    ax.axvspan(12, 24, alpha=0.05, color=ORANGE)
    ax.text(3, max(total) + 3, 'Phase 1:\nFoundation', ha='center', fontsize=8, color=BLUE)
    ax.text(9, max(total) + 3, 'Phase 2:\nCommercial Launch', ha='center', fontsize=8, color=GREEN)
    ax.text(18, max(total) + 3, 'Phase 3:\nScale & Series A', ha='center', fontsize=8, color=ORANGE)

    plt.tight_layout()
    plt.savefig(CHART_DIR / 'headcount_growth.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Generated: {CHART_DIR / 'headcount_growth.png'}")


def chart_cost_breakdown():
    """Pie chart of 24-month cost allocation and annual cost stacked bars."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle('Cost Structure Analysis', fontsize=14, fontweight='bold', color=NAVY)

    # Left: 24-month allocation pie
    categories = ['Personnel\n(70%)', 'AI & Cloud\n(6%)', 'Equipment\n(6%)',
                  'Travel\n(4%)', 'Marketing\n(4%)', 'G&A\n(7%)', 'Reserve\n(3%)']
    sizes = [3508, 308, 276, 216, 203, 364, 125]
    colors_pie = [NAVY, LIGHT_BLUE, BLUE, GREEN, ORANGE, GRAY, LIGHT_GRAY]
    explode = (0.05, 0, 0, 0, 0, 0, 0)

    wedges, texts, autotexts = ax1.pie(sizes, explode=explode, labels=categories,
                                        autopct=lambda pct: f'EUR {int(pct/100*sum(sizes))}K',
                                        colors=colors_pie, startangle=90,
                                        textprops={'fontsize': 8})
    for autotext in autotexts:
        autotext.set_fontsize(7)
        autotext.set_color('white')
    ax1.set_title('24-Month Fund Allocation\n(EUR 5M Total)', fontsize=11, color=NAVY)

    # Right: Annual cost stacked bars
    years = ['Year 1', 'Year 2', 'Year 3']
    personnel = [1203, 2305, 3200]
    infra = [103, 205, 350]
    equipment = [133, 143, 100]
    travel = [89, 127, 180]
    marketing = [83, 120, 200]
    ga = [180, 184, 200]

    bottom = np.zeros(3)
    for data, label, color in [
        (personnel, 'Personnel', NAVY),
        (infra, 'AI & Cloud', LIGHT_BLUE),
        (equipment, 'Equipment', BLUE),
        (travel, 'Travel', GREEN),
        (marketing, 'Marketing', ORANGE),
        (ga, 'G&A', GRAY),
    ]:
        ax2.bar(years, data, bottom=bottom, label=label, color=color, alpha=0.85)
        bottom += np.array(data)

    # Total labels
    totals = [sum(x) for x in zip(personnel, infra, equipment, travel, marketing, ga)]
    for i, total in enumerate(totals):
        ax2.text(i, total + 50, f'EUR {total/1000:.1f}M', ha='center', fontweight='bold',
                fontsize=9, color=NAVY)

    ax2.set_ylabel('EUR K')
    ax2.set_title('Annual Operating Costs', fontsize=11, color=NAVY)
    ax2.legend(loc='upper left', fontsize=8)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x/1000:.1f}M' if x >= 1000 else f'{x:.0f}K'))

    plt.tight_layout()
    plt.savefig(CHART_DIR / 'cost_breakdown.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Generated: {CHART_DIR / 'cost_breakdown.png'}")


def chart_revenue_scenarios():
    """Three revenue scenarios with cost overlay."""
    fig, ax = plt.subplots(figsize=(12, 5.5))
    fig.suptitle('3-Year Revenue Projections vs Operating Costs', fontsize=14, fontweight='bold', color=NAVY)

    quarters = ['Q2\n2026', 'Q3', 'Q4', 'Q1\n2027', 'Q2', 'Q3', 'Q4', 'Q1\n2028', 'Q2', 'Q3', 'Q4', 'Q1\n2029']
    x = np.arange(len(quarters))

    # Quarterly ARR (annualized from end-of-quarter cumulative customers * ACV)
    conservative_arr = [0, 100, 250, 400, 500, 700, 960, 1200, 1500, 1820, 2500, 3200]
    base_arr = [0, 150, 400, 600, 800, 1100, 1500, 2000, 2500, 3150, 4500, 5800]
    optimistic_arr = [0, 250, 600, 900, 1200, 1680, 2500, 3500, 4500, 5270, 8000, 10500]

    # Operating costs (quarterly)
    costs_quarterly = [200, 350, 450, 520, 580, 650, 770, 850, 950, 1050, 1100, 1150]

    ax.fill_between(x, conservative_arr, optimistic_arr, alpha=0.1, color=BLUE, label='_nolegend_')
    ax.plot(x, optimistic_arr, color=GREEN, linewidth=2, marker='o', markersize=4, label='Optimistic ARR')
    ax.plot(x, base_arr, color=BLUE, linewidth=2.5, marker='s', markersize=5, label='Base Case ARR')
    ax.plot(x, conservative_arr, color=ORANGE, linewidth=2, marker='^', markersize=4, label='Conservative ARR')
    ax.plot(x, costs_quarterly, color=RED, linewidth=2, linestyle='--', marker='x', markersize=5, label='Quarterly Costs')

    ax.set_xticks(x)
    ax.set_xticklabels(quarters, fontsize=8)
    ax.set_ylabel('EUR K (quarterly)')
    ax.legend(loc='upper left')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x/1000:.1f}M' if x >= 1000 else f'{x:.0f}K'))

    # Annotate break-even
    for i in range(len(base_arr)):
        if base_arr[i] > costs_quarterly[i]:
            ax.annotate('Base case\nbreak-even',
                       xy=(i, base_arr[i]),
                       xytext=(i - 1.5, base_arr[i] + 400),
                       arrowprops=dict(arrowstyle='->', color=BLUE),
                       fontsize=9, color=BLUE, fontweight='bold')
            break

    # Year dividers
    ax.axvline(x=3.5, color=GRAY, linestyle='--', alpha=0.4)
    ax.axvline(x=7.5, color=GRAY, linestyle='--', alpha=0.4)
    ax.text(1.75, max(optimistic_arr) * 0.95, 'Year 1', ha='center', color=GRAY, fontsize=9)
    ax.text(5.5, max(optimistic_arr) * 0.95, 'Year 2', ha='center', color=GRAY, fontsize=9)
    ax.text(9.5, max(optimistic_arr) * 0.95, 'Year 3', ha='center', color=GRAY, fontsize=9)

    plt.tight_layout()
    plt.savefig(CHART_DIR / 'revenue_scenarios.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Generated: {CHART_DIR / 'revenue_scenarios.png'}")


def chart_unit_economics():
    """Unit economics: CAC, LTV, payback period, gross margin."""
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle('Unit Economics & Key SaaS Metrics', fontsize=14, fontweight='bold', color=NAVY, y=1.02)

    # Top left: CAC and LTV over time
    years = ['Year 1', 'Year 2', 'Year 3']
    cac = [80, 55, 40]  # EUR K — fully loaded CAC
    ltv = [240, 360, 480]  # EUR K — 3-year LTV at avg ACV * gross margin * (1/churn)

    x_pos = np.arange(len(years))
    width = 0.35
    bars1 = ax1.bar(x_pos - width/2, cac, width, label='CAC', color=RED, alpha=0.8)
    bars2 = ax1.bar(x_pos + width/2, ltv, width, label='LTV', color=GREEN, alpha=0.8)
    ax1.set_xticks(x_pos)
    ax1.set_xticklabels(years)
    ax1.set_ylabel('EUR K')
    ax1.set_title('Customer Acquisition Cost vs Lifetime Value', fontsize=10, color=NAVY)
    ax1.legend()
    # LTV:CAC ratio labels
    for i, (c, l) in enumerate(zip(cac, ltv)):
        ax1.text(i, max(c, l) + 20, f'LTV:CAC = {l/c:.1f}x', ha='center', fontsize=9, fontweight='bold', color=NAVY)

    # Top right: Gross margin progression
    quarters = ['Q2', 'Q3', 'Q4', 'Q1', 'Q2', 'Q3', 'Q4', 'Q1', 'Q2', 'Q3', 'Q4', 'Q1']
    gross_margin = [65, 68, 72, 74, 75, 76, 77, 78, 79, 80, 81, 82]
    ax2.plot(range(len(quarters)), gross_margin, color=GREEN, linewidth=2.5, marker='o', markersize=5)
    ax2.fill_between(range(len(quarters)), gross_margin, alpha=0.15, color=GREEN)
    ax2.set_xticks(range(len(quarters)))
    ax2.set_xticklabels(quarters, fontsize=8)
    ax2.set_ylabel('Gross Margin (%)')
    ax2.set_title('Gross Margin Progression', fontsize=10, color=NAVY)
    ax2.set_ylim(60, 90)
    ax2.axhline(y=75, color=GRAY, linestyle='--', alpha=0.5)
    ax2.text(0, 76, 'SaaS benchmark: 75%', fontsize=8, color=GRAY)
    # Year labels
    ax2.axvline(x=3.5, color=GRAY, linestyle='--', alpha=0.3)
    ax2.axvline(x=7.5, color=GRAY, linestyle='--', alpha=0.3)

    # Bottom left: ARR per employee
    arr_per_emp = [0, 30, 53, 70, 80, 100, 115, 130, 150, 168, 200, 230]
    ax3.bar(range(len(quarters)), arr_per_emp, color=BLUE, alpha=0.7)
    ax3.set_xticks(range(len(quarters)))
    ax3.set_xticklabels(quarters, fontsize=8)
    ax3.set_ylabel('EUR K')
    ax3.set_title('ARR per Employee', fontsize=10, color=NAVY)
    ax3.axhline(y=150, color=GOLD, linestyle='--', alpha=0.7)
    ax3.text(0, 155, 'Target: EUR 150K/employee', fontsize=8, color=GOLD)
    ax3.axvline(x=3.5, color=GRAY, linestyle='--', alpha=0.3)
    ax3.axvline(x=7.5, color=GRAY, linestyle='--', alpha=0.3)

    # Bottom right: Monthly burn rate
    monthly_burn = [73, 79, 97, 123, 143, 159, 171, 171, 203, 213, 213, 235,
                    235, 242, 265, 271, 271, 291, 300, 311, 311, 311, 316, 316]
    monthly_rev = [0, 0, 0, 10, 20, 30, 50, 70, 90, 100, 120, 145,
                   160, 175, 200, 220, 250, 280, 320, 360, 400, 440, 480, 530]
    net_burn = [b - r for b, r in zip(monthly_burn, monthly_rev)]
    colors_bar = [RED if n > 0 else GREEN for n in net_burn]
    ax4.bar(range(24), [-n for n in net_burn], color=colors_bar, alpha=0.7)
    ax4.axhline(y=0, color='black', linewidth=0.8)
    ax4.set_xlabel('Month')
    ax4.set_ylabel('EUR K')
    ax4.set_title('Net Monthly Cash Flow (Revenue - Costs)', fontsize=10, color=NAVY)
    ax4.set_xlim(-0.5, 23.5)

    plt.tight_layout()
    plt.savefig(CHART_DIR / 'unit_economics.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Generated: {CHART_DIR / 'unit_economics.png'}")


def main():
    print("Generating financial charts...")
    chart_monthly_cashflow()
    chart_headcount_growth()
    chart_cost_breakdown()
    chart_revenue_scenarios()
    chart_unit_economics()
    print(f"\nAll charts saved to: {CHART_DIR}")


if __name__ == "__main__":
    main()
