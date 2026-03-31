#!/usr/bin/env python3
"""Generate Azirella Pitch Deck PDF from outline content."""

from fpdf import FPDF
import os

# Colors (Azirella brand — dark purple/gold theme)
BG_DARK = (18, 10, 35)       # Deep purple background
BG_SLIDE = (28, 18, 50)      # Slide background
GOLD = (218, 165, 32)         # Accent gold
WHITE = (255, 255, 255)
LIGHT_GRAY = (200, 200, 210)
MID_GRAY = (140, 140, 160)
PURPLE_ACCENT = (120, 80, 200)
GREEN = (80, 200, 120)
AMBER = (255, 180, 50)
RED = (220, 80, 80)


class PitchDeckPDF(FPDF):
    def __init__(self):
        super().__init__(orientation='L', format='A4')
        self.set_auto_page_break(auto=False)
        # Register fonts
        self.add_font('DejaVu', '', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        self.add_font('DejaVu', 'B', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
        # No italic variant available — use regular as italic fallback
        self.add_font('DejaVu', 'I', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        self.add_font('DejaVu', 'BI', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')

    def slide_bg(self):
        """Draw dark background for slide."""
        self.set_fill_color(*BG_DARK)
        self.rect(0, 0, self.w, self.h, 'F')
        # Subtle gradient bar at top
        self.set_fill_color(*PURPLE_ACCENT)
        self.rect(0, 0, self.w, 2, 'F')
        # Gold accent line
        self.set_fill_color(*GOLD)
        self.rect(0, 2, self.w, 0.5, 'F')

    def slide_title(self, title, subtitle=None, y=12):
        """Draw slide title."""
        self.set_y(y)
        self.set_font('DejaVu', 'B', 22)
        self.set_text_color(*GOLD)
        self.cell(0, 12, title, ln=True, align='L')
        if subtitle:
            self.set_font('DejaVu', 'I', 12)
            self.set_text_color(*LIGHT_GRAY)
            self.cell(0, 7, subtitle, ln=True, align='L')
        self.ln(3)

    def body_text(self, text, size=10, bold=False, color=WHITE, align='L'):
        """Write body text."""
        style = 'B' if bold else ''
        self.set_font('DejaVu', style, size)
        self.set_text_color(*color)
        self.multi_cell(0, 5.5, text, align=align)

    def bullet(self, text, indent=15, size=10, color=WHITE):
        """Write a bullet point."""
        x = self.get_x()
        self.set_x(x + indent)
        self.set_font('DejaVu', '', 8)
        self.set_text_color(*GOLD)
        self.cell(5, 5.5, '•')
        self.set_font('DejaVu', '', size)
        self.set_text_color(*color)
        self.multi_cell(self.w - x - indent - 20, 5.5, text)

    def bold_bullet(self, label, text, indent=15, size=10):
        """Write a bullet with bold label."""
        x = self.get_x()
        self.set_x(x + indent)
        self.set_font('DejaVu', '', 8)
        self.set_text_color(*GOLD)
        self.cell(5, 5.5, '•')
        self.set_font('DejaVu', 'B', size)
        self.set_text_color(*WHITE)
        label_w = self.get_string_width(label + ' ') + 1
        self.cell(label_w, 5.5, label + ' ')
        self.set_font('DejaVu', '', size)
        self.set_text_color(*LIGHT_GRAY)
        self.multi_cell(self.w - x - indent - label_w - 25, 5.5, text)

    def quote(self, text, attribution=None):
        """Draw a quote box."""
        self.set_fill_color(35, 25, 60)
        x = self.get_x() + 10
        y = self.get_y()
        self.set_fill_color(35, 25, 60)
        self.rect(x, y, self.w - 30, 18 if not attribution else 22, 'F')
        # Gold left bar
        self.set_fill_color(*GOLD)
        self.rect(x, y, 1.5, 18 if not attribution else 22, 'F')
        self.set_xy(x + 5, y + 2)
        self.set_font('DejaVu', 'I', 9)
        self.set_text_color(*LIGHT_GRAY)
        self.multi_cell(self.w - 50, 5, text)
        if attribution:
            self.set_x(x + 5)
            self.set_font('DejaVu', '', 8)
            self.set_text_color(*MID_GRAY)
            self.cell(0, 5, attribution)
        self.ln(5)

    def table_header(self, cols, widths, y=None):
        """Draw table header row."""
        if y:
            self.set_y(y)
        self.set_fill_color(40, 28, 70)
        self.set_font('DejaVu', 'B', 8)
        self.set_text_color(*GOLD)
        x = self.get_x() + 10
        for i, col in enumerate(cols):
            self.set_xy(x, self.get_y())
            self.cell(widths[i], 7, col, border=0, fill=True)
            x += widths[i]
        self.ln(7)

    def table_row(self, cols, widths, bold_first=True):
        """Draw table data row."""
        self.set_fill_color(25, 16, 45)
        x_start = self.get_x() + 10
        y_start = self.get_y()
        max_h = 6
        # Calculate max height needed
        for i, col in enumerate(cols):
            self.set_font('DejaVu', '', 8)
            lines = self.multi_cell(widths[i] - 2, 5, col, split_only=True)
            h = len(lines) * 5
            if h > max_h:
                max_h = h
        # Draw cells
        x = x_start
        for i, col in enumerate(cols):
            self.set_xy(x, y_start)
            if i == 0 and bold_first:
                self.set_font('DejaVu', 'B', 8)
                self.set_text_color(*WHITE)
            else:
                self.set_font('DejaVu', '', 8)
                self.set_text_color(*LIGHT_GRAY)
            self.cell(widths[i], max_h, '', border=0, fill=True)
            self.set_xy(x + 1, y_start)
            self.multi_cell(widths[i] - 2, 5, col)
            x += widths[i]
        self.set_y(y_start + max_h)

    def section_label(self, text, color=GOLD):
        """Small uppercase section label."""
        self.set_font('DejaVu', 'B', 8)
        self.set_text_color(*color)
        self.cell(0, 5, text.upper(), ln=True)
        self.ln(1)

    def footer_line(self):
        """Add footer with branding."""
        self.set_y(self.h - 10)
        self.set_font('DejaVu', '', 7)
        self.set_text_color(*MID_GRAY)
        self.cell(0, 5, 'AZIRELLA  |  Velocity Creates Value  |  azirella.com', align='C')

    def page_number_footer(self):
        """Add page number."""
        self.set_y(self.h - 10)
        self.set_font('DejaVu', '', 7)
        self.set_text_color(*MID_GRAY)
        self.cell(0, 5, f'{self.page_no()}', align='R')


def build_deck():
    pdf = PitchDeckPDF()
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)

    # ========== SLIDE 1: TITLE ==========
    pdf.add_page()
    pdf.slide_bg()
    # Large centered title
    pdf.set_y(55)
    pdf.set_font('DejaVu', 'B', 42)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 20, 'AZIRELLA', ln=True, align='C')
    pdf.set_font('DejaVu', 'I', 18)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.cell(0, 12, 'Velocity Creates Value', ln=True, align='C')
    pdf.ln(10)
    pdf.set_font('DejaVu', 'B', 14)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 10, 'Autonomous Supply Chain Planning', ln=True, align='C')
    pdf.set_font('DejaVu', '', 11)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.cell(0, 8, 'AI agents that make decisions, not just recommendations.', ln=True, align='C')
    pdf.ln(15)
    pdf.set_font('DejaVu', '', 9)
    pdf.set_text_color(*MID_GRAY)
    pdf.cell(0, 6, 'The first purpose-built Decision Intelligence Platform for supply chain.', ln=True, align='C')
    pdf.footer_line()

    # ========== SLIDE 2: THE PROBLEM ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.slide_title('The Problem', 'Every Monday, a planner arrives to 847 exceptions.')

    pdf.body_text('Supply chain planning is broken. Planners spend 80% of their time on reactive firefighting and 20% on strategic work. The decision cycle \u2014 from signal detection to corrective action \u2014 takes days to weeks.', size=10)
    pdf.ln(4)

    widths = [55, 95]
    pdf.table_header(['Pain Point', 'Reality'], widths)
    pdf.table_row(['Detection', 'Demand shifts discovered when someone opens a report on Tuesday'], widths)
    pdf.table_row(['Decision', '45-minute context gathering, waiting for weekly planning cycles'], widths)
    pdf.table_row(['Correction', 'Periodic replanning creates compounding errors'], widths)
    pdf.table_row(['Exceptions', '847 exceptions \u2014 most are noise, some are critical, all require triage'], widths)
    pdf.ln(5)

    # Right column stats
    pdf.set_font('DejaVu', 'B', 24)
    pdf.set_text_color(*GOLD)
    right_x = 175
    pdf.set_xy(right_x, 38)
    pdf.cell(100, 12, '80%', align='C')
    pdf.set_font('DejaVu', '', 9)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.set_xy(right_x, 50)
    pdf.cell(100, 6, 'of planner time is reactive', align='C')

    pdf.set_font('DejaVu', 'B', 24)
    pdf.set_text_color(*GOLD)
    pdf.set_xy(right_x, 62)
    pdf.cell(100, 12, '847', align='C')
    pdf.set_font('DejaVu', '', 9)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.set_xy(right_x, 74)
    pdf.cell(100, 6, 'exceptions every Monday', align='C')

    pdf.set_font('DejaVu', 'B', 24)
    pdf.set_text_color(*GOLD)
    pdf.set_xy(right_x, 86)
    pdf.cell(100, 12, 'Days', align='C')
    pdf.set_font('DejaVu', '', 9)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.set_xy(right_x, 98)
    pdf.cell(100, 6, 'from signal to action', align='C')

    pdf.set_y(135)
    pdf.quote(
        '"Planning systems have never had complete knowledge models of the supply chain they planned. The planner was the missing ontological layer."',
        '\u2014 Knut Alicke, McKinsey Partner Emeritus, KIT Karlsruhe Professor'
    )
    pdf.footer_line()

    # ========== SLIDE 3: THE OPPORTUNITY ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.slide_title('The Opportunity', 'The supply chain planning market is ripe for structural disruption.')

    pdf.body_text('Gartner published the inaugural Magic Quadrant for Decision Intelligence Platforms in January 2026, rating DI as "Transformational" \u2014 their highest impact level.', size=10)
    pdf.ln(2)
    pdf.body_text('The gap: No supply chain-native DI platform exists. MQ leaders (FICO, SAS, Aera, Quantexa) are horizontal platforms bolting on supply chain as an afterthought.', size=10, color=LIGHT_GRAY)
    pdf.ln(4)

    widths = [140, 80]
    pdf.table_header(['Market Signal', 'Source'], widths)
    pdf.table_row(['50% of SCM solutions will use intelligent agents by 2030', 'Gartner, May 2025'], widths)
    pdf.table_row(['40% of enterprise apps will include task-specific AI agents by 2026', 'Gartner, Aug 2025'], widths)
    pdf.table_row(['17% of total AI value already from agents; rising to 29% by 2028', 'BCG, Sep 2025'], widths)
    pdf.table_row(['75% of Global 500 will apply DI practices by 2026', 'Gartner CDAO Survey'], widths)
    pdf.table_row(['74% expect moderate+ agentic AI use within 2 years', 'Deloitte, 2026'], widths)
    pdf.table_row(['Only 21% have mature governance for autonomous agents', 'Deloitte, 2026'], widths)
    pdf.ln(4)

    pdf.quote(
        '"Autonomous planning has passed the peak of inflated expectations."',
        '\u2014 Gartner, November 2025'
    )
    pdf.footer_line()

    # ========== SLIDE 4: THE SOLUTION ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.slide_title('The Solution \u2014 Autonomy by Azirella', 'The first purpose-built Decision Intelligence Platform for supply chain.')

    pdf.body_text('Autonomy implements Gartner\'s full DI lifecycle \u2014 Model, Orchestrate, Monitor, Govern \u2014 natively for supply chain. Not a bolt-on. Not a copilot. A platform where AI agents own decisions by default and humans provide governance.', size=10)
    pdf.ln(5)

    pdf.section_label('THE VELOCITY EQUATION')
    widths = [60, 60, 60]
    pdf.table_header(['Phase', 'Before', 'After'], widths)
    pdf.table_row(['Detection: Signal \u2192 Awareness', 'Days to weeks', 'Seconds'], widths)
    pdf.table_row(['Decision: Awareness \u2192 Action', 'Hours to days', '<10ms'], widths)
    pdf.table_row(['Correction: Action \u2192 Outcome', 'Weekly cycles', 'Continuous'], widths)
    pdf.ln(5)

    pdf.quote(
        'BCG\'s 1/4-2-20 Rule: For every quartering of decision cycle time, labor productivity doubles and costs fall by 20%. Moving from weekly to continuous planning applies this rule repeatedly \u2014 compounding the advantage.',
        '\u2014 George Stalk Jr., "Rules of Response" (BCG Perspectives, 1987)'
    )
    pdf.ln(3)
    pdf.set_font('DejaVu', 'B', 14)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 10, 'Velocity creates value.', ln=True, align='C')
    pdf.footer_line()

    # ========== SLIDE 5: TECHNOLOGY ARCHITECTURE ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.slide_title('Technology Architecture', 'Five tiers. Eleven agents. <10ms decisions.')

    # Check if the screenshot exists
    arch_img = os.path.expanduser('~/Documents/Autonomy/docs/technology_architecture.png')
    if not os.path.exists(arch_img):
        # Try alternate locations
        for alt in ['/tmp/technology_architecture.png', os.path.expanduser('~/Pictures/technology_architecture.png')]:
            if os.path.exists(alt):
                arch_img = alt
                break

    if os.path.exists(arch_img):
        # Center the image
        img_w = 200
        x = (pdf.w - img_w) / 2
        pdf.image(arch_img, x=x, y=pdf.get_y(), w=img_w)
        pdf.set_y(pdf.get_y() + 110)
    else:
        # Draw a text representation
        pdf.ln(2)
        tiers = [
            ('CONTEXT ENGINE', 'Continuous \u2022 Multi-Channel', 'Parse \u2022 Classify \u2022 Route \u2022 Inject'),
            ('STRATEGIC \u2022 NETWORK \u2022 WEEKLY', 'Design \u2022 IBP \u2022 S&OP', 'Policies \u2022 Guardrails \u2022 KPI Targets \u2022 Risk Scoring'),
            ('TACTICAL \u2022 NETWORK \u2022 DAILY', 'Forecast \u2022 Demand \u2022 Supply \u2022 Inventory \u2022 Capacity', 'ML Baseline \u2022 Shaping \u2022 MPS/MRP \u2022 Rebalancing \u2022 Buffers'),
            ('OPERATIONAL \u2022 SITE \u2022 SHIFT', 'Per-Site Coordination', 'Cross-Function Trade-Offs \u2022 Urgency Modulation \u2022 Causal Coordination'),
            ('EXECUTION \u2022 FUNCTION \u2022 HOUR', 'Agent Hive Per Site \u2022 <10ms \u2022 A2A Protocol', 'AATP \u2022 PO \u2022 MO \u2022 TO \u2022 Quality \u2022 Maint \u2022 Rebal \u2022 OrdTrk \u2022 SubCon \u2022 FcstAdj \u2022 Buffer'),
        ]
        for tier_name, tier_desc, tier_detail in tiers:
            y = pdf.get_y()
            pdf.set_fill_color(35, 25, 60)
            pdf.rect(20, y, pdf.w - 40, 14, 'F')
            pdf.set_fill_color(*GOLD)
            pdf.rect(20, y, 2, 14, 'F')
            pdf.set_xy(25, y + 1)
            pdf.set_font('DejaVu', 'B', 7)
            pdf.set_text_color(*GOLD)
            pdf.cell(80, 5, tier_name)
            pdf.set_font('DejaVu', 'B', 7)
            pdf.set_text_color(*WHITE)
            pdf.cell(0, 5, tier_desc, ln=True)
            pdf.set_x(25)
            pdf.set_font('DejaVu', '', 6.5)
            pdf.set_text_color(*MID_GRAY)
            pdf.cell(0, 5, tier_detail, ln=True)
            pdf.ln(2)

    pdf.ln(1)
    pdf.set_font('DejaVu', 'I', 8)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.cell(0, 5, 'Context and guardrails flow down. Feedback and outcomes flow up.', ln=True, align='C')
    pdf.ln(1)
    pdf.set_font('DejaVu', '', 8)
    pdf.set_text_color(*MID_GRAY)
    pdf.cell(0, 5, 'AWS SC Data Model (35/35 entities) \u2022 SAP S/4HANA \u2022 ECC \u2022 Dynamics 365 \u2022 Odoo \u2022 Oracle \u2022 Logility \u2022 Kinaxis', ln=True, align='C')
    pdf.footer_line()

    # ========== SLIDE 6: FOUR PILLARS ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.slide_title('Four Pillars of Autonomous Planning', 'A self-reinforcing advantage that gets stronger with every decision.')

    # Four columns
    pillars = [
        ('AI Agents', '11 specialized agents as a coordinated hive. A2A protocol. <10ms inference. RL from outcomes. 24/7 operation.'),
        ('Conformal Prediction', 'Distribution-free likelihood guarantees. 95%+ coverage. Holds even when model is wrong. Zero assumptions.'),
        ('Causal AI', 'Counterfactual reasoning separates skill from luck. Training weights by causal impact, not correlation.'),
        ('Digital Twin', 'Monte Carlo across 1,000+ scenarios. 20 distribution types. Training data + calibration sets.'),
    ]
    col_w = 62
    start_x = 15
    for i, (title, desc) in enumerate(pillars):
        x = start_x + i * (col_w + 4)
        y = pdf.get_y() + 2

        # Pillar box
        pdf.set_fill_color(35, 25, 60)
        pdf.rect(x, y, col_w, 65, 'F')
        # Gold top bar
        pdf.set_fill_color(*GOLD)
        pdf.rect(x, y, col_w, 2, 'F')
        # Number
        pdf.set_xy(x + 3, y + 5)
        pdf.set_font('DejaVu', 'B', 20)
        pdf.set_text_color(*GOLD)
        pdf.cell(10, 10, str(i + 1))
        # Title
        pdf.set_xy(x + 3, y + 17)
        pdf.set_font('DejaVu', 'B', 10)
        pdf.set_text_color(*WHITE)
        pdf.multi_cell(col_w - 6, 5.5, title)
        # Desc
        pdf.set_xy(x + 3, y + 28)
        pdf.set_font('DejaVu', '', 7.5)
        pdf.set_text_color(*LIGHT_GRAY)
        pdf.multi_cell(col_w - 6, 4.5, desc)

    pdf.set_y(pdf.get_y() + 72)
    pdf.set_font('DejaVu', 'I', 9)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.cell(0, 6, 'Each capability reinforces the others, creating a self-reinforcing advantage that compounds over time.', align='C', ln=True)
    pdf.footer_line()

    # ========== SLIDE 7: DECISION STREAM ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.slide_title('The Decision Stream', 'From 847 exceptions to 14.')

    pdf.body_text('A planner arrives Monday to 847 exceptions. Autonomy\'s agents have already evaluated every one:', size=10)
    pdf.ln(3)

    # Visual breakdown
    categories = [
        ('612', 'Auto-Resolved', 'High likelihood \u2014 agent acted', GREEN),
        ('168', 'Abandoned', 'Low urgency + low likelihood', MID_GRAY),
        ('53', 'Informational', 'Handled, flagged for awareness', AMBER),
        ('14', 'Inspect & Override', 'High urgency + low likelihood', RED),
    ]
    bar_y = pdf.get_y()
    for i, (num, label, desc, color) in enumerate(categories):
        y = bar_y + i * 18
        # Number
        pdf.set_xy(20, y)
        pdf.set_font('DejaVu', 'B', 22)
        pdf.set_text_color(*color)
        pdf.cell(30, 14, num, align='R')
        # Label
        pdf.set_xy(55, y)
        pdf.set_font('DejaVu', 'B', 11)
        pdf.set_text_color(*WHITE)
        pdf.cell(60, 7, label)
        pdf.set_xy(55, y + 7)
        pdf.set_font('DejaVu', '', 8)
        pdf.set_text_color(*LIGHT_GRAY)
        pdf.cell(100, 7, desc)

    # Right side: smart triage
    pdf.set_xy(170, bar_y)
    pdf.section_label('SMART TRIAGE LOGIC')
    pdf.set_x(170)
    pdf.set_font('DejaVu', '', 8)
    pdf.set_text_color(*LIGHT_GRAY)
    triage = [
        'High likelihood + any urgency \u2192 Agent acts',
        'Low urgency + low likelihood \u2192 Abandoned',
        'High urgency + low likelihood \u2192 Human review',
    ]
    for t in triage:
        pdf.set_x(170)
        pdf.cell(0, 6, t, ln=True)
        pdf.ln(1)

    pdf.set_y(bar_y + 78)
    pdf.set_font('DejaVu', 'B', 11)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 8, 'She\'s not processing exceptions. She\'s managing decisions.', ln=True, align='C')
    pdf.ln(3)
    pdf.body_text('Every override becomes Experiential Knowledge \u2014 the system learns the pattern, not just the correction. The system literally gets smarter every hour.', size=9, color=LIGHT_GRAY)
    pdf.footer_line()

    # ========== SLIDE 8: ADOPTION CURVE ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.slide_title('Trust Through Measurement', 'Adoption builds through measured outcomes, not arbitrary timelines.')

    # Adoption metrics
    metrics = [
        ('Week 1', '~45%', '~35%', '~20%'),
        ('Week 12', '~72%', '~18%', '~10%'),
        ('Steady State', '~85%', '<10%', '~5%'),
    ]
    widths = [50, 45, 45, 45]
    pdf.table_header(['Period', 'Auto-Executed', 'Human Override', 'Abandoned'], widths)
    for row in metrics:
        pdf.table_row(list(row), widths)
    pdf.ln(6)

    pdf.section_label('THREE-LEVEL MATURITY PROGRESSION')
    levels = [
        ('Level 1: Decision Support', 'Human in the loop. System provides data, insights, scenarios. All decisions require human input.'),
        ('Level 2: Decision Augmentation', 'Human on the loop. Agents recommend, humans inspect and override. Every override captured and scored.'),
        ('Level 3: Decision Automation', 'Human out of the loop. Agents execute within guardrails. Full auditability. Progression governed by calibrated likelihood and decision quality metrics.'),
    ]
    for label, desc in levels:
        pdf.bold_bullet(label, desc, indent=10, size=9)
        pdf.ln(1)

    pdf.ln(3)
    pdf.quote(
        'Gartner: Demand planning can be automated to the point that "90% of the process is handled without human involvement."'
    )
    pdf.footer_line()

    # ========== SLIDE 9: PLANNER'S DAY ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.slide_title('A Planner\'s Day \u2014 Transformed', 'From exception processing to strategic decision-making.')

    # Two columns
    col_w = 125
    # WITHOUT
    pdf.set_fill_color(40, 20, 20)
    pdf.rect(15, pdf.get_y(), col_w, 95, 'F')
    y_start = pdf.get_y()
    pdf.set_xy(18, y_start + 2)
    pdf.set_font('DejaVu', 'B', 10)
    pdf.set_text_color(*RED)
    pdf.cell(col_w - 6, 6, 'WITHOUT AUTONOMY: Reactive Firefighting')
    pdf.set_font('DejaVu', '', 7)
    pdf.set_text_color(*MID_GRAY)
    pdf.set_xy(18, y_start + 9)
    pdf.cell(col_w - 6, 5, '80% reactive  \u2022  20% strategic')

    without = [
        ('7:00', 'Arrive to 847 exceptions across the network'),
        ('7:30', 'Export data to spreadsheets for analysis'),
        ('9:00', 'Triage exceptions \u2014 most are noise'),
        ('11:00', 'Chase suppliers and ops teams for updates'),
        ('13:00', 'Manual adjustments across 3 systems'),
        ('15:00', 'Prepare slides for S&OP meeting'),
        ('17:00', 'Leave knowing weekend backlog will be worse'),
    ]
    for i, (time, task) in enumerate(without):
        pdf.set_xy(20, y_start + 17 + i * 10)
        pdf.set_font('DejaVu', 'B', 7)
        pdf.set_text_color(*MID_GRAY)
        pdf.cell(15, 5, time)
        pdf.set_font('DejaVu', '', 7.5)
        pdf.set_text_color(*LIGHT_GRAY)
        pdf.cell(col_w - 22, 5, task)

    # WITH
    pdf.set_fill_color(20, 35, 25)
    pdf.rect(145, y_start, col_w, 95, 'F')
    pdf.set_xy(148, y_start + 2)
    pdf.set_font('DejaVu', 'B', 10)
    pdf.set_text_color(*GREEN)
    pdf.cell(col_w - 6, 6, 'WITH AUTONOMY: Strategic Governance')
    pdf.set_font('DejaVu', '', 7)
    pdf.set_text_color(*MID_GRAY)
    pdf.set_xy(148, y_start + 9)
    pdf.cell(col_w - 6, 5, '20% governance  \u2022  80% strategic')

    with_auto = [
        ('7:00', 'Open Decision Stream \u2014 14 decisions need judgment'),
        ('7:30', 'Review agent reasoning, override where expertise adds value'),
        ('9:00', 'Check Value Dashboard \u2014 agents saved $47K overnight'),
        ('10:00', 'Strategic session: demand shaping scenarios for Q3'),
        ('13:00', 'Coach junior planners on override patterns'),
        ('15:00', 'Review agent accuracy, calibrate guardrails for NPI'),
        ('17:00', 'Leave knowing agents continue through the night'),
    ]
    for i, (time, task) in enumerate(with_auto):
        pdf.set_xy(150, y_start + 17 + i * 10)
        pdf.set_font('DejaVu', 'B', 7)
        pdf.set_text_color(*MID_GRAY)
        pdf.cell(15, 5, time)
        pdf.set_font('DejaVu', '', 7.5)
        pdf.set_text_color(*LIGHT_GRAY)
        pdf.cell(col_w - 22, 5, task)

    pdf.set_y(y_start + 100)
    pdf.set_font('DejaVu', 'B', 11)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 8, 'Agents handle the repetitive. You do the creative.', ln=True, align='C')
    pdf.footer_line()

    # ========== SLIDE 10: DI PLATFORM ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.slide_title('Decision Intelligence Platform', 'Autonomy vs. horizontal DIPs \u2014 purpose-built for supply chain.')

    widths = [55, 80, 80]
    pdf.table_header(['Capability', 'Horizontal DIPs', 'Autonomy'], widths)
    rows = [
        ['Decision Modeling', 'Generic business rules', 'Domain-specific sequential framework \u2014 11 agent definitions'],
        ['Decision Orchestration', 'Rules engines, workflow', 'Real-time agents (<10ms), A2A protocol, 25+ negotiation scenarios'],
        ['Decision Monitoring', 'BI dashboards', 'Calibrated likelihood + quality scoring + drift triggers'],
        ['Decision Governance', 'Audit logs', 'Causal AI \u2014 counterfactual override evaluation'],
        ['Supply Chain Domain', 'Bolt-on or absent', 'Native (35 AWS SC entities, 8 policy types)'],
        ['Agentic AI', 'Early/experimental', '11 production agents per site, multi-site coordination'],
        ['Probabilistic Planning', 'Limited', '21 distributions, Monte Carlo, forecast quality scoring'],
        ['Learning from Overrides', 'Basic', 'Causal AI \u2014 learn from impact, not correlation'],
    ]
    for row in rows:
        pdf.table_row(row, widths)

    pdf.ln(5)
    pdf.body_text('Decisions as First-Class Digital Assets: Every recurring decision is a trackable digital asset with defined inputs, explicit logic, clear ownership, measurable outcomes, and feedback loops for continuous improvement.', size=9, bold=True, color=LIGHT_GRAY)
    pdf.footer_line()

    # ========== SLIDE 11: MEASURABLE VALUE ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.slide_title('Measurable Value \u2014 Not Promises', 'Every decision evaluated in financial terms. Value is measured, not projected.')

    # Big numbers row
    big_stats = [
        ('20\u201335%', 'Cost\nReduction'),
        ('+4%', 'Revenue\nGrowth'),
        ('-20%', 'Inventory\nReduction'),
        ('<10ms', 'Decision\nLatency'),
        ('24/7', 'Continuous\nOperation'),
    ]
    stat_w = 50
    start_x = 17
    y = pdf.get_y() + 2
    for i, (num, label) in enumerate(big_stats):
        x = start_x + i * (stat_w + 4)
        pdf.set_fill_color(35, 25, 60)
        pdf.rect(x, y, stat_w, 30, 'F')
        pdf.set_fill_color(*GOLD)
        pdf.rect(x, y, stat_w, 1.5, 'F')
        pdf.set_xy(x, y + 3)
        pdf.set_font('DejaVu', 'B', 18)
        pdf.set_text_color(*GOLD)
        pdf.cell(stat_w, 10, num, align='C')
        pdf.set_xy(x, y + 15)
        pdf.set_font('DejaVu', '', 8)
        pdf.set_text_color(*LIGHT_GRAY)
        pdf.multi_cell(stat_w, 4.5, label, align='C')

    pdf.set_y(y + 38)
    pdf.section_label('FOUR MEASUREMENT DIMENSIONS')
    dims = [
        ('Decision Savings', 'Every agent decision tracks cost avoided, revenue protected, waste eliminated'),
        ('Balanced Scorecard', 'Financial, customer, operational, strategic metrics with P10/P50/P90 distributions'),
        ('Sparkline Tracking', 'Decision quality, override effectiveness, agent accuracy trends at a glance'),
        ('ROI Before vs. After', 'Continuous baseline comparison shows exactly what Autonomy delivers'),
    ]
    for label, desc in dims:
        pdf.bold_bullet(label + ' \u2014', desc, indent=10, size=9)
        pdf.ln(1)

    pdf.ln(3)
    pdf.body_text('McKinsey: Autonomous planning delivers +4% revenue growth, -20% inventory reduction, -10% supply chain costs.', size=8, color=MID_GRAY)
    pdf.footer_line()

    # ========== SLIDE 12: SOLUTIONS ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.slide_title('Solutions', 'Same platform, same AI agents \u2014 configured for your supply chain position.')

    solutions = [
        ('Manufacturer', 'Multi-tier production planning with BOM explosion, capacity constraints, make-vs-buy decisions, and quality management. MPS through shop floor execution. 11 agents coordinate manufacturing, procurement, quality, and maintenance at machine speed.'),
        ('Distributor', 'Multi-echelon inventory optimization, cross-DC rebalancing, demand-driven replenishment, and last-mile allocation. Purpose-built for wholesale and food distribution with perishability, shelf-life optimization, and route-level fulfillment.'),
        ('Retailer', 'Multi-channel allocation, promotional demand management, seasonal pre-build, and store-level replenishment. Omnichannel fulfillment with channel-specific allocation agents balancing e-commerce, wholesale, and store inventory in real time.'),
    ]
    for title, desc in solutions:
        pdf.set_fill_color(35, 25, 60)
        y = pdf.get_y()
        pdf.rect(15, y, pdf.w - 30, 28, 'F')
        pdf.set_fill_color(*GOLD)
        pdf.rect(15, y, 2, 28, 'F')
        pdf.set_xy(22, y + 3)
        pdf.set_font('DejaVu', 'B', 11)
        pdf.set_text_color(*GOLD)
        pdf.cell(0, 6, title)
        pdf.set_xy(22, y + 10)
        pdf.set_font('DejaVu', '', 8)
        pdf.set_text_color(*LIGHT_GRAY)
        pdf.multi_cell(pdf.w - 50, 4.5, desc)
        pdf.ln(4)

    pdf.ln(3)
    pdf.section_label('INTEGRATION')
    pdf.body_text('AWS SC Data Model (35/35 entities)  \u2022  SAP S/4HANA & ECC  \u2022  Dynamics 365  \u2022  Odoo v18  \u2022  Oracle  \u2022  Logility  \u2022  Kinaxis  \u2022  Delta/net change loading  \u2022  AI schema validation  \u2022  Zero proprietary formats', size=8, color=LIGHT_GRAY)
    pdf.footer_line()

    # ========== SLIDE 13: RESEARCH FOUNDATION ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.slide_title('Research Foundation', 'Grounded in peer-reviewed research and industry frameworks.')

    widths = [45, 55, 115]
    pdf.table_header(['Domain', 'Foundation', 'Application in Autonomy'], widths)
    research = [
        ['Decision Intelligence', 'Gartner DIP (MQ Jan 2026)', 'Full DI lifecycle: model, orchestrate, monitor, govern'],
        ['Sequential Decisions', 'Powell\'s Unified Framework', 'Five decision elements structure the agent hierarchy'],
        ['Conformal Prediction', 'Vovk et al. (distribution-free)', 'Calibrated likelihood guarantees on every agent decision'],
        ['Causal AI', 'Counterfactual reasoning', 'Separates skill from luck in agent evaluation'],
        ['Stochastic Planning', 'Monte Carlo simulation', '1,000+ scenarios, 20 distribution types'],
        ['Agentic AI', 'BCG/Deloitte research', '11 production agents, A2A protocol'],
    ]
    for row in research:
        pdf.table_row(row, widths)

    pdf.ln(6)
    pdf.quote(
        '"AI automates tasks, not purpose. Tasks get automated, but humans still own outcomes."',
        '\u2014 Jensen Huang, CEO, NVIDIA'
    )
    pdf.footer_line()

    # ========== SLIDE 14: TEAM ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.slide_title('Founding Team')

    pdf.set_font('DejaVu', 'B', 16)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 10, 'Trevor Miles \u2014 CEO & Founder', ln=True)
    pdf.ln(2)

    pdf.set_font('DejaVu', 'B', 12)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 8, '30+ years in supply chain planning technology', ln=True)
    pdf.ln(3)

    roles = [
        ('VP of Thought Leadership, Kinaxis', 'Shaped the narrative for S&OP and concurrent planning'),
        ('Chief Strategy Officer, Daybreak', 'Strategic leadership in supply chain technology'),
        ('i2 Technologies', 'Early career in supply chain optimization'),
        ('PhD (ABD), Industrial Engineering', 'Penn State University'),
        ('MSc, Chemical Engineering', ''),
    ]
    for role, desc in roles:
        pdf.bold_bullet(role, desc if desc else '', indent=10, size=10)
        pdf.ln(2)

    pdf.ln(5)
    pdf.set_fill_color(35, 25, 60)
    y = pdf.get_y()
    pdf.rect(15, y, pdf.w - 30, 20, 'F')
    pdf.set_fill_color(*GOLD)
    pdf.rect(15, y, pdf.w - 30, 1.5, 'F')
    pdf.set_xy(20, y + 5)
    pdf.set_font('DejaVu', 'I', 10)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.multi_cell(pdf.w - 45, 5.5, 'Core conviction: The planning function is due for structural inversion. The enabling technology now exists. Agents own decisions by default; humans provide governance.')
    pdf.footer_line()

    # ========== SLIDE 15: THE ASK ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.slide_title('The Ask', 'Velocity creates value. We\'re ready to prove it at scale.')

    pdf.section_label('WHAT WE\'VE BUILT')
    built = [
        'Production platform with 11 autonomous agents',
        'Four demo tenants (SAP S/4HANA, Dynamics 365, Odoo, Food Distribution)',
        'AWS SC Data Model compliance (35/35 entities)',
        'SOC II compliant architecture (RLS, pgaudit, tenant isolation)',
        'Conformal prediction with distribution-free guarantees',
        'Causal AI for counterfactual decision evaluation',
        'Decision Stream with urgency/likelihood scoring',
        'Azirella voice assistant with full supply chain context',
    ]
    for item in built:
        pdf.bullet(item, indent=10, size=9)
        pdf.ln(0.5)

    pdf.ln(4)
    pdf.section_label('WHAT WE NEED')
    needs = [
        'Seed funding to accelerate GTM and land first enterprise customers',
        'AWS Marketplace listing (ISV Accelerate program)',
        'Expand engineering team for multi-region deployment',
    ]
    for item in needs:
        pdf.bullet(item, indent=10, size=9)
        pdf.ln(0.5)

    pdf.ln(4)
    pdf.section_label('TARGET MARKET')
    pdf.body_text('Mid-market manufacturers, distributors, and retailers seeking enterprise-grade supply chain planning without enterprise-scale costs or implementation timelines.', size=9, color=LIGHT_GRAY)
    pdf.footer_line()

    # ========== SLIDE 16: CLOSING ==========
    pdf.add_page()
    pdf.slide_bg()
    pdf.set_y(40)
    pdf.set_font('DejaVu', 'I', 12)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.cell(0, 10, 'The value isn\'t in any single decision \u2014 it\'s in decision velocity.', ln=True, align='C')
    pdf.ln(8)

    lines = [
        ('Detecting signals in ', 'seconds', ', not days.'),
        ('Correcting course ', 'continuously', ', not weekly.'),
        ('Compressing the decision cycle from ', 'weeks to moments', '.'),
    ]
    for pre, bold, post in lines:
        pdf.set_font('DejaVu', '', 13)
        pdf.set_text_color(*WHITE)
        w1 = pdf.get_string_width(pre)
        w2 = pdf.get_string_width(bold)
        w3 = pdf.get_string_width(post)
        total = w1 + w2 + w3
        x = (pdf.w - total) / 2
        pdf.set_x(x)
        pdf.cell(w1, 10, pre)
        pdf.set_font('DejaVu', 'B', 13)
        pdf.set_text_color(*GOLD)
        pdf.cell(w2, 10, bold)
        pdf.set_font('DejaVu', '', 13)
        pdf.set_text_color(*WHITE)
        pdf.cell(w3, 10, post, ln=True)
        pdf.ln(2)

    pdf.ln(5)
    pdf.set_font('DejaVu', '', 10)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.cell(0, 8, 'While every decision remains explainable, overrideable, and measured.', ln=True, align='C')

    pdf.ln(10)
    pdf.set_font('DejaVu', 'B', 12)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 8, '5 tiers  \u2022  11 agents  \u2022  20\u201335% cost reduction', ln=True, align='C')

    pdf.ln(12)
    pdf.set_font('DejaVu', 'B', 36)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 18, 'AZIRELLA', ln=True, align='C')
    pdf.set_font('DejaVu', 'I', 16)
    pdf.set_text_color(*LIGHT_GRAY)
    pdf.cell(0, 10, 'Velocity Creates Value', ln=True, align='C')

    pdf.ln(8)
    pdf.set_font('DejaVu', '', 10)
    pdf.set_text_color(*MID_GRAY)
    pdf.cell(0, 6, 'azirella.com  |  azirella.com/demo', ln=True, align='C')
    pdf.set_font('DejaVu', '', 8)
    pdf.cell(0, 6, '\u00a9 2026 Azirella Ltd. All rights reserved. Cyprus.', ln=True, align='C')
    pdf.footer_line()

    # Output
    output_path = os.path.expanduser('~/Documents/Autonomy/Azirella_Pitch_Deck.pdf')
    pdf.output(output_path)
    print(f'PDF generated: {output_path}')
    print(f'Pages: {pdf.page_no()}')


if __name__ == '__main__':
    build_deck()
