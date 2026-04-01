#!/usr/bin/env python3
"""Generate Azirella Customer Pitch Deck PDF — no technical jargon."""

from fpdf import FPDF
import os

# Brand colors
BG_DARK = (18, 10, 35)
GOLD = (218, 165, 32)
WHITE = (255, 255, 255)
LIGHT_GRAY = (200, 200, 210)
MID_GRAY = (140, 140, 160)
PURPLE_ACCENT = (120, 80, 200)
GREEN = (80, 200, 120)
AMBER = (255, 180, 50)
RED = (220, 80, 80)
BOX_BG = (35, 25, 60)
ROW_BG = (25, 16, 45)
HEADER_BG = (40, 28, 70)


class DeckPDF(FPDF):
    def __init__(self):
        super().__init__(orientation='L', format='A4')
        self.set_auto_page_break(auto=False)
        self.add_font('DJ', '', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        self.add_font('DJ', 'B', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
        # Use regular as italic fallback
        self.add_font('DJ', 'I', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')

    def bg(self):
        self.set_fill_color(*BG_DARK)
        self.rect(0, 0, self.w, self.h, 'F')
        self.set_fill_color(*PURPLE_ACCENT)
        self.rect(0, 0, self.w, 2, 'F')
        self.set_fill_color(*GOLD)
        self.rect(0, 2, self.w, 0.5, 'F')

    def footer_brand(self):
        self.set_y(self.h - 10)
        self.set_font('DJ', '', 7)
        self.set_text_color(*MID_GRAY)
        self.cell(0, 5, f'AZIRELLA  |  Velocity Creates Value  |  azirella.com', align='C')

    def title_slide(self, title, subtitle=None, y=12):
        self.set_y(y)
        self.set_font('DJ', 'B', 22)
        self.set_text_color(*GOLD)
        self.cell(0, 12, title, new_x='LMARGIN', new_y='NEXT', align='L')
        if subtitle:
            self.set_font('DJ', 'I', 11)
            self.set_text_color(*LIGHT_GRAY)
            self.cell(0, 7, subtitle, new_x='LMARGIN', new_y='NEXT', align='L')
        self.ln(3)

    def text(self, t, sz=10, bold=False, color=WHITE, align='L'):
        self.set_font('DJ', 'B' if bold else '', sz)
        self.set_text_color(*color)
        self.multi_cell(0, 5.5, t, align=align)

    def bullet(self, t, indent=15, sz=9, color=WHITE):
        x = self.get_x()
        self.set_x(x + indent)
        self.set_font('DJ', '', 8)
        self.set_text_color(*GOLD)
        self.cell(5, 5.5, '\u2022')
        self.set_font('DJ', '', sz)
        self.set_text_color(*color)
        self.multi_cell(self.w - x - indent - 20, 5.5, t)

    def bold_bullet(self, label, desc, indent=15, sz=9):
        x = self.get_x()
        self.set_x(x + indent)
        self.set_font('DJ', '', 8)
        self.set_text_color(*GOLD)
        self.cell(5, 5.5, '\u2022')
        self.set_font('DJ', 'B', sz)
        self.set_text_color(*WHITE)
        lw = self.get_string_width(label + ' ') + 1
        self.cell(lw, 5.5, label + ' ')
        self.set_font('DJ', '', sz)
        self.set_text_color(*LIGHT_GRAY)
        self.multi_cell(self.w - x - indent - lw - 25, 5.5, desc)

    def label(self, t, color=GOLD):
        self.set_font('DJ', 'B', 8)
        self.set_text_color(*color)
        self.cell(0, 5, t.upper(), new_x='LMARGIN', new_y='NEXT')
        self.ln(1)

    def quote(self, t, attr=None):
        x, y = self.get_x() + 10, self.get_y()
        h = 18 if not attr else 22
        self.set_fill_color(*BOX_BG)
        self.rect(x, y, self.w - 30, h, 'F')
        self.set_fill_color(*GOLD)
        self.rect(x, y, 1.5, h, 'F')
        self.set_xy(x + 5, y + 2)
        self.set_font('DJ', 'I', 9)
        self.set_text_color(*LIGHT_GRAY)
        self.multi_cell(self.w - 50, 5, t)
        if attr:
            self.set_x(x + 5)
            self.set_font('DJ', '', 8)
            self.set_text_color(*MID_GRAY)
            self.cell(0, 5, attr)
        self.ln(5)

    def tbl_hdr(self, cols, widths):
        self.set_fill_color(*HEADER_BG)
        self.set_font('DJ', 'B', 8)
        self.set_text_color(*GOLD)
        x = self.get_x() + 10
        for i, c in enumerate(cols):
            self.set_xy(x, self.get_y())
            self.cell(widths[i], 7, c, fill=True)
            x += widths[i]
        self.ln(7)

    def tbl_row(self, cols, widths, bold_first=True):
        self.set_fill_color(*ROW_BG)
        xs, ys = self.get_x() + 10, self.get_y()
        # calc height
        mx = 6
        for i, c in enumerate(cols):
            self.set_font('DJ', '', 8)
            lines = len(self.multi_cell(widths[i] - 2, 5, c, dry_run=True, output='LINES'))
            mx = max(mx, lines * 5)
        x = xs
        for i, c in enumerate(cols):
            self.set_xy(x, ys)
            if i == 0 and bold_first:
                self.set_font('DJ', 'B', 8)
                self.set_text_color(*WHITE)
            else:
                self.set_font('DJ', '', 8)
                self.set_text_color(*LIGHT_GRAY)
            self.cell(widths[i], mx, '', fill=True)
            self.set_xy(x + 1, ys)
            self.multi_cell(widths[i] - 2, 5, c)
            x += widths[i]
        self.set_y(ys + mx)

    def big_stat(self, x, y, num, label):
        self.set_fill_color(*BOX_BG)
        w = 48
        self.rect(x, y, w, 28, 'F')
        self.set_fill_color(*GOLD)
        self.rect(x, y, w, 1.5, 'F')
        self.set_xy(x, y + 3)
        self.set_font('DJ', 'B', 18)
        self.set_text_color(*GOLD)
        self.cell(w, 10, num, align='C')
        self.set_xy(x, y + 15)
        self.set_font('DJ', '', 7.5)
        self.set_text_color(*LIGHT_GRAY)
        self.multi_cell(w, 4, label, align='C')


def build():
    pdf = DeckPDF()
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)

    # ===== SLIDE 1: TITLE =====
    pdf.add_page()
    pdf.bg()
    pdf.set_y(50)
    pdf.set_font('DJ', 'B', 42)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 20, 'AZIRELLA', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.set_font('DJ', 'I', 18)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.cell(0, 12, 'Velocity Creates Value', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.ln(10)
    pdf.set_font('DJ', 'B', 14)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 10, 'Autonomous Supply Chain Planning', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.set_font('DJ', '', 11)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.cell(0, 8, 'AI agents that make decisions, not just recommendations.', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.ln(12)
    pdf.set_font('DJ', '', 9)
    pdf.set_text_color(*MID_GRAY)
    pdf.cell(0, 6, 'Decision Intelligence for Supply Chain Planning', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.cell(0, 6, 'Explore the opportunity with us.', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.footer_brand()

    # ===== SLIDE 2: THE PROBLEM =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('The Planning Problem You Live Every Day', 'Every Monday morning starts the same way.')

    pdf.text('Your planners arrive to hundreds of exceptions. Most are noise. Some are critical. All require triage. The weekly planning cycle creates a backlog that compounds \u2014 Friday\'s supplier delay becomes Monday\'s 847 exceptions.', sz=10)
    pdf.ln(4)

    w = [55, 100]
    pdf.tbl_hdr(['What Happens Today', 'The Cost'], w)
    pdf.tbl_row(['Demand shifts discovered days later', 'Lost revenue, excess inventory'], w)
    pdf.tbl_row(['45-min context gathering per decision', 'Planner time wasted on data, not decisions'], w)
    pdf.tbl_row(['Weekly replanning compounds errors', 'Small misses become large misses'], w)
    pdf.tbl_row(['80% of planner time is firefighting', 'Strategic work never gets done'], w)
    pdf.ln(4)

    # Big stats on right
    pdf.big_stat(180, 38, '80%', 'of planner time\nis reactive')
    pdf.big_stat(180, 70, '847', 'exceptions\nevery Monday')
    pdf.big_stat(180, 102, 'Days', 'from signal\nto action')

    pdf.set_y(138)
    pdf.quote(
        '"Planning systems have never had complete knowledge models of the supply chain they planned. The planner was the missing ontological layer."',
        '\u2014 Knut Alicke, McKinsey Partner Emeritus'
    )
    pdf.footer_brand()

    # ===== SLIDE 3: THE SHIFT =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('The Shift \u2014 From Reactive to Autonomous', 'The planning function is undergoing a structural transformation.')

    pdf.text('Gartner published the inaugural Magic Quadrant for Decision Intelligence Platforms in January 2026, rating DI as "Transformational" \u2014 their highest impact level.', sz=10)
    pdf.ln(3)

    pdf.label('THREE STAGES OF PLANNING MATURITY')
    w = [55, 100, 55]
    pdf.tbl_hdr(['Stage', 'How It Works', 'Your Role'], w)
    pdf.tbl_row(['Decision Support', 'System provides data and reports. You make every decision.', 'Doing the work'], w)
    pdf.tbl_row(['Decision Augmentation', 'AI recommends with reasoning. You inspect and override.', 'Guiding the work'], w)
    pdf.tbl_row(['Decision Automation', 'Agents act within your guardrails. You govern outcomes.', 'Leading the business'], w)
    pdf.ln(4)

    w2 = [145, 75]
    pdf.tbl_hdr(['Market Signal', 'Source'], w2)
    pdf.tbl_row(['50% of SCM solutions will use intelligent agents by 2030', 'Gartner, May 2025'], w2)
    pdf.tbl_row(['74% of enterprises expect significant agentic AI use within 2 years', 'Deloitte, 2026'], w2)
    pdf.tbl_row(['Only 21% have mature governance for autonomous agents', 'Deloitte, 2026'], w2)
    pdf.footer_brand()

    # ===== SLIDE 4: THE SOLUTION =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('Introducing Autonomy', 'The first purpose-built Decision Intelligence Platform for supply chain planning.')

    pdf.text('Autonomy doesn\'t replace your planners \u2014 it elevates what they do. AI agents handle the repetitive decisions at machine speed while your team focuses on the strategic decisions that create competitive advantage.', sz=10)
    pdf.ln(4)

    pdf.label('THE VELOCITY EQUATION \u2014 COMPRESSING THE TIME BETWEEN SIGNAL AND ACTION')
    w = [70, 55, 55]
    pdf.tbl_hdr(['Phase', 'Today', 'With Autonomy'], w)
    pdf.tbl_row(['Detection: When do you know?', 'Days to weeks', 'Seconds'], w)
    pdf.tbl_row(['Decision: How fast can you act?', 'Hours to days', 'Immediate'], w)
    pdf.tbl_row(['Correction: How often do you adjust?', 'Weekly cycles', 'Continuous'], w)
    pdf.ln(4)

    pdf.quote(
        'BCG\'s 1/4-2-20 Rule: For every quartering of decision cycle time, labor productivity doubles and costs fall by 20%.',
        '\u2014 George Stalk Jr., BCG Perspectives'
    )
    pdf.ln(2)
    pdf.set_font('DJ', 'B', 14)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 10, 'The value isn\'t in any single decision \u2014 it\'s in decision velocity.', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.footer_brand()

    # ===== SLIDE 5: DECISION STREAM =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('How It Works \u2014 The Decision Stream', 'Agents surface decisions. You provide judgment.')

    pdf.text('Instead of processing hundreds of exceptions, your Decision Stream shows only what matters. Every decision scored on urgency and confidence.', sz=10)
    pdf.ln(3)

    pdf.label('A TYPICAL MONDAY MORNING WITH AUTONOMY')
    cats = [
        ('612', 'Auto-Resolved', 'Agent confident, acted autonomously overnight', GREEN),
        ('168', 'Abandoned', 'Low urgency, low confidence \u2014 no action warranted', MID_GRAY),
        ('53', 'Informational', 'Handled, flagged so you\'re aware', AMBER),
        ('14', 'Your Attention', 'High urgency, agent uncertain \u2014 your judgment needed', RED),
    ]
    by = pdf.get_y()
    for i, (n, lbl, desc, clr) in enumerate(cats):
        y = by + i * 16
        pdf.set_xy(20, y)
        pdf.set_font('DJ', 'B', 20)
        pdf.set_text_color(*clr)
        pdf.cell(28, 12, n, align='R')
        pdf.set_xy(52, y)
        pdf.set_font('DJ', 'B', 10)
        pdf.set_text_color(*WHITE)
        pdf.cell(55, 6, lbl)
        pdf.set_xy(52, y + 6)
        pdf.set_font('DJ', '', 8)
        pdf.set_text_color(*LIGHT_GRAY)
        pdf.cell(140, 6, desc)

    pdf.set_y(by + 70)
    pdf.set_font('DJ', 'B', 11)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 8, 'Your planner focuses on 14 decisions where their expertise makes the difference.', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.ln(3)
    pdf.text('Every override teaches the system. The pattern is captured as Experiential Knowledge \u2014 your team\'s behavioral expertise, preserved and applied to future decisions.', sz=9, color=LIGHT_GRAY)
    pdf.footer_brand()

    # ===== SLIDE 6: ARCHITECTURE =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('Technology Architecture', 'Six layers. Eleven agents. Decisions in milliseconds.')

    # Check for image
    arch_img = None
    for p in ['docs/technology_architecture.png', '/tmp/technology_architecture.png']:
        fp = os.path.join(os.path.expanduser('~/Documents/Autonomy'), p) if not p.startswith('/') else p
        if os.path.exists(fp):
            arch_img = fp
            break

    if arch_img:
        iw = 200
        pdf.image(arch_img, x=(pdf.w - iw) / 2, y=pdf.get_y(), w=iw)
        pdf.set_y(pdf.get_y() + 105)
    else:
        layers = [
            ('CONTEXT ENGINE', 'Continuous \u2022 Multi-Channel', 'Ingests ERP signals, email, external data, IoT \u2014 classifies and routes to the right decision tier'),
            ('STRATEGIC \u2022 NETWORK', 'Weekly', 'Policies, guardrails, KPI targets, risk scoring \u2014 Design, IBP, S&OP'),
            ('TACTICAL \u2022 NETWORK', 'Daily', 'Forecast, demand shaping, supply balancing, inventory targets, capacity planning'),
            ('OPERATIONAL \u2022 SITE', 'Hourly', 'Cross-function trade-offs, urgency modulation, bottleneck detection, cascade prevention'),
            ('EXECUTION \u2022 SITE & ROLE', 'Milliseconds', '11 agents per site \u2014 ATP, purchase orders, manufacturing, quality, maintenance, rebalancing'),
            ('ERP INTEGRATION', 'Delta/Net Change', 'SAP, Dynamics, Odoo, Oracle \u2014 AI schema matching, no proprietary formats'),
        ]
        for name, cadence, desc in layers:
            y = pdf.get_y()
            pdf.set_fill_color(*BOX_BG)
            pdf.rect(20, y, pdf.w - 40, 14, 'F')
            pdf.set_fill_color(*GOLD)
            pdf.rect(20, y, 2, 14, 'F')
            pdf.set_xy(25, y + 1)
            pdf.set_font('DJ', 'B', 7)
            pdf.set_text_color(*GOLD)
            pdf.cell(70, 5, name)
            pdf.set_font('DJ', 'B', 7)
            pdf.set_text_color(*WHITE)
            pdf.cell(35, 5, cadence)
            pdf.set_font('DJ', '', 6.5)
            pdf.set_text_color(*MID_GRAY)
            pdf.cell(0, 5, desc, new_x='LMARGIN', new_y='NEXT')
            pdf.ln(3)

    pdf.ln(1)
    pdf.set_font('DJ', 'I', 9)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.cell(0, 5, 'Context and guardrails flow down. Feedback and outcomes flow up.', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.footer_brand()

    # ===== SLIDE 7: FOUR PILLARS =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('Four Pillars \u2014 Why Autonomy Works', 'A self-reinforcing advantage that gets stronger with every decision.')

    pillars = [
        ('Autonomous\nAI Agents', '11 specialized agents per site. Each handles focused decisions \u2014 allocation, purchasing, rebalancing, quality \u2014 at machine speed, 24/7. Every decision is explainable and overrideable.'),
        ('Conformal\nPrediction', 'Every decision carries a mathematically calibrated confidence score. Coverage guarantees hold regardless of data distribution. When confidence drops, decisions escalate for review.'),
        ('Causal AI', 'Counterfactual reasoning separates good decisions from lucky outcomes. Your system learns from skill, not coincidence. Overrides that improve outcomes get higher training weight.'),
        ('ERP-Specific\nDigital Twin', 'A complete simulation calibrated from your actual ERP data. Generates thousands of scenarios for training and calibration. Agents learn on your business before acting on it.'),
    ]
    cw = 62
    sx = 15
    for i, (title, desc) in enumerate(pillars):
        x = sx + i * (cw + 4)
        y = pdf.get_y() + 2
        pdf.set_fill_color(*BOX_BG)
        pdf.rect(x, y, cw, 70, 'F')
        pdf.set_fill_color(*GOLD)
        pdf.rect(x, y, cw, 2, 'F')
        # Number
        pdf.set_xy(x + 3, y + 5)
        pdf.set_font('DJ', 'B', 18)
        pdf.set_text_color(*GOLD)
        pdf.cell(10, 8, str(i + 1))
        # Title
        pdf.set_xy(x + 3, y + 15)
        pdf.set_font('DJ', 'B', 9)
        pdf.set_text_color(*WHITE)
        pdf.multi_cell(cw - 6, 5, title)
        # Desc
        pdf.set_xy(x + 3, y + 30)
        pdf.set_font('DJ', '', 7)
        pdf.set_text_color(*LIGHT_GRAY)
        pdf.multi_cell(cw - 6, 4.2, desc)

    pdf.set_y(pdf.get_y() + 76)
    pdf.set_font('DJ', 'I', 9)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.cell(0, 6, 'Each pillar reinforces the others \u2014 the advantage compounds over time.', align='C', new_x='LMARGIN', new_y='NEXT')
    pdf.footer_brand()

    # ===== SLIDE 8: PLANNER'S DAY =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('A Planner\'s Day \u2014 Transformed', 'From exception processing to strategic decision-making.')

    cw = 125
    # WITHOUT
    ys = pdf.get_y()
    pdf.set_fill_color(40, 20, 20)
    pdf.rect(15, ys, cw, 95, 'F')
    pdf.set_xy(18, ys + 2)
    pdf.set_font('DJ', 'B', 10)
    pdf.set_text_color(*RED)
    pdf.cell(cw - 6, 6, 'WITHOUT AUTONOMY: Reactive Firefighting')
    pdf.set_xy(18, ys + 9)
    pdf.set_font('DJ', '', 7)
    pdf.set_text_color(*MID_GRAY)
    pdf.cell(cw - 6, 5, '80% reactive  \u2022  20% strategic')

    without = [
        ('7:00', 'Arrive to 847 exceptions across the network'),
        ('7:30', 'Export data to spreadsheets for analysis'),
        ('9:00', 'Triage exceptions \u2014 most are noise'),
        ('11:00', 'Chase suppliers and ops teams for updates'),
        ('1:00', 'Manual adjustments across 3 systems'),
        ('3:00', 'Prepare slides for S&OP meeting'),
        ('5:00', 'Leave knowing weekend backlog will be worse'),
    ]
    for i, (t, task) in enumerate(without):
        pdf.set_xy(20, ys + 17 + i * 10)
        pdf.set_font('DJ', 'B', 7)
        pdf.set_text_color(*MID_GRAY)
        pdf.cell(13, 5, t)
        pdf.set_font('DJ', '', 7.5)
        pdf.set_text_color(*LIGHT_GRAY)
        pdf.cell(cw - 20, 5, task)

    # WITH
    pdf.set_fill_color(20, 35, 25)
    pdf.rect(145, ys, cw, 95, 'F')
    pdf.set_xy(148, ys + 2)
    pdf.set_font('DJ', 'B', 10)
    pdf.set_text_color(*GREEN)
    pdf.cell(cw - 6, 6, 'WITH AUTONOMY: Strategic Governance')
    pdf.set_xy(148, ys + 9)
    pdf.set_font('DJ', '', 7)
    pdf.set_text_color(*MID_GRAY)
    pdf.cell(cw - 6, 5, '20% governance  \u2022  80% strategic')

    with_a = [
        ('7:00', 'Open Decision Stream \u2014 14 decisions need judgment'),
        ('7:30', 'Review agent reasoning, override where expertise adds value'),
        ('9:00', 'Check Value Dashboard \u2014 agents saved $47K overnight'),
        ('10:00', 'Strategic session: demand shaping scenarios for Q3'),
        ('1:00', 'Coach junior planners on decision patterns'),
        ('3:00', 'Review agent performance, calibrate for new product launch'),
        ('5:00', 'Leave knowing agents continue through the night'),
    ]
    for i, (t, task) in enumerate(with_a):
        pdf.set_xy(150, ys + 17 + i * 10)
        pdf.set_font('DJ', 'B', 7)
        pdf.set_text_color(*MID_GRAY)
        pdf.cell(13, 5, t)
        pdf.set_font('DJ', '', 7.5)
        pdf.set_text_color(*LIGHT_GRAY)
        pdf.cell(cw - 20, 5, task)

    pdf.set_y(ys + 100)
    pdf.set_font('DJ', 'B', 11)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 8, 'Agents handle the repetitive. You do the creative.', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.footer_brand()

    # ===== SLIDE 9: TRUST =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('Trust Through Measurement', 'Adoption builds through measured outcomes \u2014 not promises.')

    w = [50, 50, 45, 65]
    pdf.tbl_hdr(['Period', 'Agent Handles', 'Human Reviews', 'Result'], w)
    pdf.tbl_row(['Week 1', '~45%', '~35%', 'Learning your patterns'], w)
    pdf.tbl_row(['Week 12', '~72%', '~18%', 'Earning trust through results'], w)
    pdf.tbl_row(['Steady State', '~85%', '<10%', 'Fully autonomous within guardrails'], w)
    pdf.ln(5)

    pdf.label('EVERY DECISION IS MEASURED IN FOUR DIMENSIONS')
    dims = [
        ('Decision Savings \u2014', 'Cost avoided, revenue protected, waste eliminated \u2014 tracked per decision'),
        ('Balanced Scorecard \u2014', 'Financial, customer, operational, strategic KPIs with confidence ranges'),
        ('Trend Tracking \u2014', 'Decision quality, override effectiveness, agent accuracy at a glance'),
        ('Before vs. After \u2014', 'Continuous baseline comparison showing exactly what Autonomy delivers'),
    ]
    for l, d in dims:
        pdf.bold_bullet(l, d, indent=10, sz=9)
        pdf.ln(1)

    pdf.ln(3)
    pdf.quote('Gartner: Demand planning can be automated to the point that "90% of the process is handled without human involvement."')
    pdf.footer_brand()

    # ===== SLIDE 10: COMPETITIVE LANDSCAPE =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('Competitive Landscape', 'What makes Autonomy different from what you\'ve seen before.')

    w = [52, 52, 55, 60]
    pdf.tbl_hdr(['Capability', 'Traditional Planning', 'Copilot / AI Assistants', 'Autonomy'], w)
    rows = [
        ['Decision Ownership', 'Human makes all decisions', 'AI recommends, human decides', 'Agent decides within guardrails, human governs'],
        ['Decision Speed', 'Weekly/daily cycles', 'Faster recommendations', 'Millisecond execution, continuous'],
        ['Confidence Scoring', 'None or heuristic', 'Heuristic confidence', 'Conformal prediction \u2014 mathematically guaranteed'],
        ['Learning from Overrides', 'None', 'Basic feedback', 'Causal AI \u2014 learns from impact, not correlation'],
        ['Simulation & Training', 'Static scenarios', 'Limited what-if', 'ERP-specific Digital Twin \u2014 thousands of scenarios'],
        ['AI-Native Architecture', 'Monolithic engine', 'AI layer on legacy', '6 layers: Context, Strategic, Tactical, Operational, Execution, Integration'],
        ['Continuous Operation', 'Business hours', 'On-demand', '24/7 \u2014 agents never sleep'],
        ['Measurable ROI', 'Annual benchmarks', 'Estimated savings', 'Per-decision financial tracking'],
    ]
    for r in rows:
        pdf.tbl_row(r, w)
    pdf.footer_brand()

    # ===== SLIDE 11: MEASURABLE IMPACT =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('Measurable Impact', 'Results you can quantify from day one.')

    # Big stat boxes
    stats = [
        ('20\u201335%', 'Supply Chain\nCost Reduction'),
        ('+4%', 'Revenue\nGrowth'),
        ('-20%', 'Inventory\nReduction'),
        ('847\u219214', 'Exceptions\nto Decisions'),
        ('24/7', 'Continuous\nOperation'),
    ]
    sy = pdf.get_y() + 2
    for i, (n, l) in enumerate(stats):
        pdf.big_stat(17 + i * 52, sy, n, l)

    pdf.set_y(sy + 35)
    pdf.text('Every agent decision tracks cost avoided, revenue protected, and waste eliminated. The executive dashboard shows savings trends, decision quality, and agent performance \u2014 no drilling required.', sz=9, color=LIGHT_GRAY)
    pdf.ln(4)

    w = [80, 140]
    pdf.tbl_hdr(['Metric', 'Expected Impact'], w)
    pdf.tbl_row(['Planner time on strategy', '20% \u2192 80%'], w)
    pdf.tbl_row(['Decision cycle time', 'Weeks \u2192 continuous'], w)
    pdf.tbl_row(['Autonomous decision rate', '~85% at steady state'], w)
    pdf.tbl_row(['Overnight value', 'Agents operate 24/7 \u2014 no weekends, no holidays'], w)
    pdf.ln(3)

    pdf.text('McKinsey: Autonomous planning delivers +4% revenue growth, -20% inventory reduction, -10% supply chain costs.', sz=8, color=MID_GRAY)
    pdf.footer_brand()

    # ===== SLIDE 12: INDUSTRIES =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('Built for Your Industry', 'Same platform, same AI agents \u2014 configured for your supply chain.')

    solutions = [
        ('Manufacturer', 'Multi-tier production planning with bill-of-materials management, capacity constraints, make-vs-buy decisions, and quality management. From master production scheduling through shop floor execution. Agents coordinate manufacturing, procurement, quality, and maintenance decisions at machine speed.'),
        ('Distributor', 'Multi-echelon inventory optimization, cross-warehouse rebalancing, demand-driven replenishment, and last-mile allocation. Purpose-built for wholesale and food distribution with perishability management, shelf-life optimization, and route-level fulfillment.'),
        ('Retailer', 'Multi-channel allocation, promotional demand management, seasonal pre-build, and store-level replenishment. Omnichannel fulfillment with channel-specific agents balancing e-commerce, wholesale, and store inventory in real time.'),
    ]
    for title, desc in solutions:
        y = pdf.get_y()
        pdf.set_fill_color(*BOX_BG)
        pdf.rect(15, y, pdf.w - 30, 28, 'F')
        pdf.set_fill_color(*GOLD)
        pdf.rect(15, y, 2, 28, 'F')
        pdf.set_xy(22, y + 3)
        pdf.set_font('DJ', 'B', 11)
        pdf.set_text_color(*GOLD)
        pdf.cell(0, 6, title)
        pdf.set_xy(22, y + 10)
        pdf.set_font('DJ', '', 8)
        pdf.set_text_color(*LIGHT_GRAY)
        pdf.multi_cell(pdf.w - 50, 4.5, desc)
        pdf.ln(4)

    pdf.ln(2)
    pdf.label('ERP INTEGRATION')
    pdf.text('SAP S/4HANA & ECC  \u2022  Microsoft Dynamics 365  \u2022  Odoo  \u2022  Oracle  \u2022  AI schema matching  \u2022  Delta/net change loading  \u2022  No proprietary lock-in', sz=8, color=LIGHT_GRAY)
    pdf.footer_brand()

    # ===== SLIDE 13: GETTING STARTED =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('Getting Started', 'From first conversation to autonomous operation in weeks.')

    w = [40, 35, 145]
    pdf.tbl_hdr(['Phase', 'Timeline', 'What Happens'], w)
    pdf.tbl_row(['Discovery', 'Week 1\u20132', 'Map your supply chain, identify high-value decision areas, define success metrics'], w)
    pdf.tbl_row(['Integration', 'Week 2\u20134', 'Connect your ERP, AI schema mapping, data validation'], w)
    pdf.tbl_row(['Digital Twin', 'Week 4\u20136', 'Calibrate simulation from your data, train agents on your supply chain'], w)
    pdf.tbl_row(['Go Live', 'Week 6\u20138', 'Decision augmentation \u2014 agents recommend, your team reviews and overrides'], w)
    pdf.tbl_row(['Autonomous', 'Week 8+', 'Trust builds through measured outcomes. Auto-execution rate climbs as confidence grows'], w)
    pdf.ln(5)

    pdf.set_font('DJ', 'B', 11)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 8, 'No multi-year implementation. No army of consultants. No rip-and-replace.', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.ln(3)
    pdf.text('Your team starts seeing value in weeks because agents learn from your data and your decisions \u2014 not from a generic model.', sz=10, color=LIGHT_GRAY)
    pdf.footer_brand()

    # ===== SLIDE 14: AZIRELLA ASSISTANT =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('The Azirella Assistant', 'Ask questions in plain language. Get answers grounded in your live data.')

    pdf.text('Every page in Autonomy includes the Azirella Assistant \u2014 a conversational AI that understands your supply chain context. Ask about inventory levels, supplier performance, or what to prioritize today. Activate voice mode for hands-free operation.', sz=10)
    pdf.ln(5)

    pdf.label('STRATEGY BRIEFINGS')
    pdf.text('AI-generated executive briefings on your cadence \u2014 weekly, daily, or on demand. Each briefing compares the current state to the prior period, identifies what changed, flags governance issues, and recommends where leadership attention will have the most impact.', sz=9, color=LIGHT_GRAY)
    pdf.ln(5)

    pdf.set_font('DJ', 'B', 12)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 8, 'No slides to build. No reports to chase.', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.ln(5)

    pdf.label('WHAT YOUR PEERS ARE ASKING')
    questions = [
        '"How would this work with our SAP / Dynamics / Odoo environment?"',
        '"What does the first 90 days look like?"',
        '"How do we measure ROI from day one?"',
        '"How do our planners\' expertise get captured and preserved?"',
    ]
    for q in questions:
        pdf.bullet(q, indent=10, sz=9, color=LIGHT_GRAY)
        pdf.ln(1)
    pdf.footer_brand()

    # ===== SLIDE 15: RESEARCH =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('Research Foundation', 'Grounded in peer-reviewed research \u2014 not hype.')

    w = [55, 165]
    pdf.tbl_hdr(['Domain', 'What It Means for You'], w)
    pdf.tbl_row(['Decision Intelligence', 'Implements the full lifecycle Gartner identified as "Transformational" \u2014 model, orchestrate, monitor, govern'], w)
    pdf.tbl_row(['Conformal Prediction', 'Confidence scores carry mathematical guarantees, not guesswork'], w)
    pdf.tbl_row(['Causal AI', 'The system learns what actually works, not what coincided with good outcomes'], w)
    pdf.tbl_row(['Sequential Decisions', 'Structured decisions with tracked inputs, logic, ownership, and outcomes'], w)
    pdf.tbl_row(['Stochastic Planning', 'Plans account for uncertainty \u2014 because the real world isn\'t deterministic'], w)
    pdf.ln(5)

    pdf.quote(
        '"AI automates tasks, not purpose. Tasks get automated, but humans still own outcomes."',
        '\u2014 Jensen Huang, CEO, NVIDIA'
    )
    pdf.footer_brand()

    # ===== SLIDE 16: LET'S EXPLORE =====
    pdf.add_page()
    pdf.bg()
    pdf.title_slide('Let\'s Explore the Opportunity', 'Decision Intelligence for supply chain planning is here.')

    pdf.text('We invite you to explore what autonomous planning could mean for your business:', sz=11)
    pdf.ln(4)

    options = [
        ('See It Live \u2014', 'A guided demonstration using a supply chain configured to your industry'),
        ('Value Assessment \u2014', 'Quantify the potential impact on your specific planning challenges'),
        ('Pilot Program \u2014', 'Start with a focused use case and expand as trust builds'),
    ]
    for l, d in options:
        pdf.bold_bullet(l, d, indent=10, sz=10)
        pdf.ln(3)

    pdf.ln(5)
    pdf.set_fill_color(*BOX_BG)
    y = pdf.get_y()
    pdf.rect(15, y, pdf.w - 30, 22, 'F')
    pdf.set_fill_color(*GOLD)
    pdf.rect(15, y, pdf.w - 30, 1.5, 'F')
    pdf.set_xy(20, y + 4)
    pdf.set_font('DJ', '', 10)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.multi_cell(pdf.w - 45, 5.5, 'We\'re ready to answer your questions with your data, your supply chain, and your decision challenges.')

    pdf.footer_brand()

    # ===== SLIDE 17: CLOSING =====
    pdf.add_page()
    pdf.bg()
    pdf.set_y(40)
    pdf.set_font('DJ', 'I', 12)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.cell(0, 10, 'The value isn\'t in any single decision \u2014 it\'s in decision velocity.', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.ln(8)

    lines = [
        ('Detecting signals in ', 'seconds', ', not days.'),
        ('Correcting course ', 'continuously', ', not weekly.'),
        ('Compressing the decision cycle from ', 'weeks to moments', '.'),
    ]
    for pre, bold, post in lines:
        pdf.set_font('DJ', '', 13)
        pdf.set_text_color(*WHITE)
        w1 = pdf.get_string_width(pre)
        w2 = pdf.get_string_width(bold)
        w3 = pdf.get_string_width(post)
        x = (pdf.w - w1 - w2 - w3) / 2
        pdf.set_x(x)
        pdf.cell(w1, 10, pre)
        pdf.set_font('DJ', 'B', 13)
        pdf.set_text_color(*GOLD)
        pdf.cell(w2, 10, bold)
        pdf.set_font('DJ', '', 13)
        pdf.set_text_color(*WHITE)
        pdf.cell(w3, 10, post, new_x='LMARGIN', new_y='NEXT')
        pdf.ln(2)

    pdf.ln(4)
    pdf.set_font('DJ', '', 10)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.cell(0, 8, 'While every decision remains explainable, overrideable, and measured.', new_x='LMARGIN', new_y='NEXT', align='C')

    pdf.ln(8)
    pdf.set_font('DJ', 'B', 12)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 8, 'Agents handle the repetitive. You do the creative.', new_x='LMARGIN', new_y='NEXT', align='C')

    pdf.ln(10)
    pdf.set_font('DJ', 'B', 36)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 18, 'AZIRELLA', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.set_font('DJ', 'I', 16)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.cell(0, 10, 'Velocity Creates Value', new_x='LMARGIN', new_y='NEXT', align='C')

    pdf.ln(6)
    pdf.set_font('DJ', '', 10)
    pdf.set_text_color(*MID_GRAY)
    pdf.cell(0, 6, 'azirella.com  |  azirella.com/demo', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.set_font('DJ', '', 8)
    pdf.cell(0, 6, '\u00a9 2026 Azirella Ltd. All rights reserved.', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.footer_brand()

    out = os.path.expanduser('~/Documents/Autonomy/Azirella_Customer_Pitch_Deck.pdf')
    pdf.output(out)
    print(f'PDF generated: {out}')
    print(f'Pages: {pdf.page_no()}')


if __name__ == '__main__':
    build()
