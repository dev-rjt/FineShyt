from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables" / "M1.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

PAGE_W, PAGE_H = A4
INK = colors.HexColor("#102D2A")
MUTED = colors.HexColor("#55706A")
GREEN = colors.HexColor("#067A55")
GREEN_DARK = colors.HexColor("#075A45")
MINT = colors.HexColor("#E8F5EF")
MINT_2 = colors.HexColor("#F4FAF7")
GOLD = colors.HexColor("#D99A2B")
GOLD_LIGHT = colors.HexColor("#FFF4DB")
LINE = colors.HexColor("#C8DDD4")
WHITE = colors.white


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="TitleM1", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=24, leading=27, textColor=INK, alignment=TA_LEFT,
    spaceAfter=4,
))
styles.add(ParagraphStyle(
    name="Deck", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=9.2, leading=13.2, textColor=MUTED, spaceAfter=0,
))
styles.add(ParagraphStyle(
    name="Section", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=12.5, leading=15, textColor=INK, spaceBefore=3, spaceAfter=5,
))
styles.add(ParagraphStyle(
    name="Kicker", parent=styles["BodyText"], fontName="Helvetica-Bold",
    fontSize=7.2, leading=9, textColor=GREEN, tracking=1.2,
))
styles.add(ParagraphStyle(
    name="BodyM1", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=8.2, leading=11.6, textColor=INK, spaceAfter=3,
))
styles.add(ParagraphStyle(
    name="BodySmall", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=7.2, leading=9.7, textColor=INK,
))
styles.add(ParagraphStyle(
    name="SmallMuted", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=6.7, leading=8.8, textColor=MUTED,
))
styles.add(ParagraphStyle(
    name="CardTitle", parent=styles["BodyText"], fontName="Helvetica-Bold",
    fontSize=8.2, leading=10, textColor=GREEN_DARK, spaceAfter=2,
))
styles.add(ParagraphStyle(
    name="TableHead", parent=styles["BodyText"], fontName="Helvetica-Bold",
    fontSize=6.9, leading=8.5, textColor=WHITE,
))
styles.add(ParagraphStyle(
    name="TableBody", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=6.5, leading=8.4, textColor=INK,
))
styles.add(ParagraphStyle(
    name="TableBodyBold", parent=styles["BodyText"], fontName="Helvetica-Bold",
    fontSize=6.6, leading=8.5, textColor=INK,
))
styles.add(ParagraphStyle(
    name="CenterSmall", parent=styles["BodyText"], fontName="Helvetica-Bold",
    fontSize=7, leading=8.5, textColor=INK, alignment=TA_CENTER,
))


def footer_header(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 7.4)
    canvas.drawString(15 * mm, PAGE_H - 12 * mm, "TEAM NUMBER 5")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica-Bold", 7.2)
    canvas.drawRightString(PAGE_W - 15 * mm, PAGE_H - 12 * mm, "M1 APPROACH | 10 OCTOBER 2026")
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.7)
    canvas.line(15 * mm, PAGE_H - 15 * mm, PAGE_W - 15 * mm, PAGE_H - 15 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 6.7)
    canvas.drawString(15 * mm, 9 * mm, "Glass-Box Green Customer Insights")
    canvas.drawRightString(PAGE_W - 15 * mm, 9 * mm, f"{doc.page} / 2")
    canvas.restoreState()


class ArchitectureFlow(Flowable):
    def __init__(self, width):
        super().__init__()
        self.width = width
        self.height = 45 * mm

    def _box(self, x, y, w, h, title, body, fill):
        c = self.canv
        c.setFillColor(fill)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.7)
        c.roundRect(x, y, w, h, 5, fill=1, stroke=1)
        p = Paragraph(f"<b>{title}</b><br/><font color='#55706A'>{body}</font>", styles["CenterSmall"])
        pw, ph = p.wrap(w - 8, h - 8)
        p.drawOn(c, x + 4, y + (h - ph) / 2)

    def _arrow(self, x1, y, x2):
        c = self.canv
        c.setStrokeColor(GREEN)
        c.setFillColor(GREEN)
        c.setLineWidth(1.2)
        c.line(x1, y, x2 - 4, y)
        c.line(x2 - 8, y + 3, x2 - 4, y)
        c.line(x2 - 8, y - 3, x2 - 4, y)

    def draw(self):
        gap = 7
        w = (self.width - 3 * gap) / 4
        h = 16 * mm
        top_y = self.height - h - 2
        bottom_y = 1
        row1 = [
            ("Hybrid data", "public seeds + synthetic banking"),
            ("Categorise", "8 exclusive transaction classes"),
            ("Customer 360", "one cutoff-safe feature row"),
            ("Predict", "4 propensities + confidence + reasons"),
        ]
        row2 = [
            ("Rules gate", "eligible / blocked / review"),
            ("Impact engine", "deterministic estimate or abstain"),
            ("JSON contract", "schema, versions, audit trail"),
            ("Explain + act", "verified wording and dashboard"),
        ]
        for i, (title, body) in enumerate(row1):
            x = i * (w + gap)
            self._box(x, top_y, w, h, title, body, MINT_2 if i < 3 else GOLD_LIGHT)
            if i < 3:
                self._arrow(x + w, top_y + h / 2, x + w + gap)
        for i, (title, body) in enumerate(row2):
            x = i * (w + gap)
            self._box(x, bottom_y, w, h, title, body, MINT if i < 3 else GOLD_LIGHT)
            if i < 3:
                self._arrow(x + w, bottom_y + h / 2, x + w + gap)
        c = self.canv
        x_start = self.width - w / 2
        x_target = w / 2
        mid_y = (top_y + bottom_y + h) / 2
        c.setStrokeColor(GREEN)
        c.setLineWidth(1.2)
        c.line(x_start, top_y, x_start, mid_y)
        c.line(x_start, mid_y, x_target, mid_y)
        c.line(x_target, mid_y, x_target, bottom_y + h + 4)
        c.line(x_target - 3, bottom_y + h + 8, x_target, bottom_y + h + 4)
        c.line(x_target + 3, bottom_y + h + 8, x_target, bottom_y + h + 4)


def pill_row():
    items = [
        ("GP01", "EV Finance", "fuel + mileage"),
        ("GP02", "Green Home Loan", "home + energy"),
        ("GP03", "Solar Finance", "ownership + electricity"),
        ("GP04", "Paperless Banking", "paper + digital activity"),
    ]
    cells = []
    for code, name, signal in items:
        cells.append(Paragraph(
            f"<font color='#067A55'><b>{code}</b></font><br/><b>{name}</b><br/><font color='#55706A'>{signal}</font>",
            styles["CenterSmall"],
        ))
    t = Table([cells], colWidths=[42.5 * mm] * 4, rowHeights=[15 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MINT_2),
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.7, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def principle_strip():
    cells = [
        Paragraph("<font color='#FFFFFF'><b>ML predicts</b></font><br/><font color='#BFD8CF'>take-up likelihood</font>", styles["CenterSmall"]),
        Paragraph("<font color='#FFFFFF'><b>Rules decide</b></font><br/><font color='#BFD8CF'>whether to show</font>", styles["CenterSmall"]),
        Paragraph("<font color='#FFFFFF'><b>Code calculates</b></font><br/><font color='#BFD8CF'>potential impact</font>", styles["CenterSmall"]),
        Paragraph("<font color='#FFFFFF'><b>LLM explains</b></font><br/><font color='#BFD8CF'>approved facts only</font>", styles["CenterSmall"]),
    ]
    t = Table([cells], colWidths=[42.5 * mm] * 4, rowHeights=[13 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INK),
        ("TEXTCOLOR", (0, 0), (-1, -1), WHITE),
        ("INNERGRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#31544E")),
        ("BOX", (0, 0), (-1, -1), 0.7, INK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def approach_cards():
    cards = [
        ("01  DATA FOUNDATION", "Build a reproducible 5,000-customer hybrid dataset: bounded public-source patterns plus synthetic banking, vehicle and behavioural records. Use a fixed cutoff, 90-day outcome window and customer-level 70/15/15 split. Document provenance, missingness and category boundaries."),
        ("02  MODELS + EVIDENCE", "Classify merchant text with character TF-IDF and logistic regression against an ordered-rule baseline. Train one validation-selected LightGBM / logistic blend per product; calibrate probabilities and emit a separate confidence score plus fixed local reason codes."),
        ("03  SAFE DECISIONING", "Run product-specific tri-state rules after scoring: ELIGIBLE, INELIGIBLE or MANUAL_REVIEW. A high score cannot override a failed rule. Compute potential annual impact in deterministic code using versioned UK factors, explicit assumptions, ranges and abstention when inputs are missing."),
        ("04  EXPLANATION + EXPERIENCE", "Package every customer-product result in JSON schema v1.0.0 with audit metadata. Give the LLM only this approved payload; verify numbers and product mapping, then fall back to a deterministic template on failure. Serve customer, manager, what-if, model-health and trust views."),
    ]
    rows = []
    for i in range(0, 4, 2):
        row = []
        for title, body in cards[i:i + 2]:
            row.append([Paragraph(title, styles["CardTitle"]), Paragraph(body, styles["BodySmall"])])
        rows.append(row)
    t = Table(rows, colWidths=[84 * mm, 84 * mm], rowHeights=[34 * mm, 34 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MINT_2),
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.7, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def testing_table():
    rows = [
        [Paragraph("Layer", styles["TableHead"]), Paragraph("Method and split discipline", styles["TableHead"]), Paragraph("Evidence / failure cases", styles["TableHead"])],
        [Paragraph("Data", styles["TableBodyBold"]), Paragraph("Deterministic build; schema, range, foreign-key, cutoff and customer-split checks; labels remain post-cutoff.", styles["TableBody"]), Paragraph("Rebuild with seed 42; assert no leakage, complete four-product labels, public-source provenance and deliberate missing/conflict scenarios.", styles["TableBody"])],
        [Paragraph("Transaction model", styles["TableBodyBold"]), Paragraph("Evaluate only validation/test customers; per-class precision, recall and F1, macro-F1, accuracy and confusion matrix.", styles["TableBody"]), Paragraph("Compare with keyword rules; test unknown/noisy merchants and Fuel vs Automotive, Electricity/Gas vs Utilities boundaries.", styles["TableBody"])],
        [Paragraph("Propensity", styles["TableBodyBold"]), Paragraph("5-fold CV on train only; validation for calibration, blend and threshold; untouched test for AUC, PR-AUC, log loss, Brier, top-10% lift and bootstrap CI.", styles["TableBody"]), Paragraph("Compare logistic and prevalence baselines; inspect train-test gap, calibration, confidence completeness/support and subgroup recommendation rates.", styles["TableBody"])],
        [Paragraph("Rules + impact", styles["TableBodyBold"]), Paragraph("Unit and golden-value tests for each rule, formula, unit, factor and time horizon; same input must reproduce the same output.", styles["TableBody"]), Paragraph("High score but blocked; existing EV/solar; non-homeowner; missing mileage/energy; insufficient-data abstention; separate paper/digital metrics from CO2e.", styles["TableBody"])],
        [Paragraph("Explanation + system", styles["TableBodyBold"]), Paragraph("Schema-validate every record; structured-payload grounding tests; latency and rerun checks; customer and manager acceptance walkthroughs.", styles["TableBody"]), Paragraph("Reject unsupported numbers, wrong product, eligibility promises and omitted uncertainty; verify safe fallback, audit versions and human-review routing.", styles["TableBody"])],
    ]
    t = Table(rows, colWidths=[25 * mm, 75 * mm, 68 * mm], repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN_DARK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, MINT_2]),
        ("BOX", (0, 0), (-1, -1), 0.65, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.45, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def safeguards():
    left = Paragraph(
        "<b>Responsible AI boundary</b><br/>No real or confidential banking data. Propensity is not approval. Eligibility rules are illustrative until replaced by authorised criteria. Estimates are not measured reductions; every customer action remains subject to human oversight.",
        styles["BodySmall"],
    )
    right = Paragraph(
        "<b>M1 success definition</b><br/>One reproducible path for all four required opportunities, with traceable evidence, blocked and missing-data cases, documented impact provenance, grounded explanations, separate business/customer views and rerunnable evaluation artifacts.",
        styles["BodySmall"],
    )
    t = Table([[left, right]], colWidths=[84 * mm, 84 * mm], rowHeights=[25 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), GOLD_LIGHT),
        ("BACKGROUND", (1, 0), (1, 0), MINT),
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.7, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def build():
    frame = Frame(15 * mm, 14 * mm, PAGE_W - 30 * mm, PAGE_H - 32 * mm, leftPadding=0, rightPadding=0, topPadding=6, bottomPadding=0)
    template = PageTemplate(id="M1", frames=[frame], onPage=footer_header)
    doc = BaseDocTemplate(
        str(OUT), pagesize=A4, pageTemplates=[template],
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=18 * mm, bottomMargin=14 * mm,
        title="M1 Approach - Glass-Box Green Customer Insights",
        author="Team Number 5",
        subject="Megathon X M1 approach submission",
    )

    story = [
        Spacer(1, 4 * mm),
        Paragraph("M1 / APPROACH", styles["Kicker"]),
        Paragraph("Glass-Box Green Customer Insights", styles["TitleM1"]),
        Paragraph("A traceable AI platform that finds relevant green-finance opportunities, checks whether they may be shown, estimates potential sustainability impact and explains every action with evidence.", styles["Deck"]),
        Spacer(1, 4 * mm),
        Paragraph("1. Problem statement and our understanding", styles["Section"]),
        Paragraph("The challenge is not merely to rank customers or add a chatbot. It is to join transactions, products, energy, vehicle and digital behaviour into a Customer 360; identify the four mandatory opportunities; quantify potential impact transparently; and serve useful customer and business insights without confusing behavioural propensity with financial eligibility.", styles["BodyM1"]),
        Spacer(1, 1.5 * mm),
        pill_row(),
        Spacer(1, 3 * mm),
        principle_strip(),
        Spacer(1, 4 * mm),
        Paragraph("2. Idea / abstract", styles["Section"]),
        Paragraph("We propose a modular, auditable decision pipeline. ML performs only two jobs: transaction categorisation and product take-up prediction. A separate rule engine can block or route a case for review; a deterministic impact engine uses documented factors and returns a range or an honest insufficient-data result. A versioned JSON contract then constrains the explanation layer and powers both a customer explorer and a business dashboard. This separation makes every score, exclusion, estimate and sentence inspectable.", styles["BodyM1"]),
        Spacer(1, 2 * mm),
        Paragraph("3. High-level pipeline / architecture", styles["Section"]),
        ArchitectureFlow(170 * mm),
        Spacer(1, 1.5 * mm),
        Paragraph("<b>Control invariant:</b> a high propensity never overrides a failed product rule; an LLM never predicts, calculates impact or decides eligibility. Missing evidence routes to abstention or human review.", styles["SmallMuted"]),
        PageBreak(),
        Spacer(1, 4 * mm),
        Paragraph("4. Delivery approach", styles["Section"]),
        approach_cards(),
        Spacer(1, 4 * mm),
        Paragraph("5. Planned testing methodology", styles["Section"]),
        Paragraph("Testing follows the same component boundaries as the architecture. Model selection is kept separate from final assessment, and scenario tests target the failure modes the brief says evaluators may exercise.", styles["BodyM1"]),
        testing_table(),
        Spacer(1, 4 * mm),
        safeguards(),
        Spacer(1, 3 * mm),
        Paragraph("<b>Planned evidence pack:</b> validation report, held-out model metrics and baselines, test predictions, schema-valid opportunity records, factor catalogue, rule/impact unit tests, explanation-grounding set, limitations note and a reproducible run command.", styles["SmallMuted"]),
    ]
    doc.build(story)
    print(OUT)


if __name__ == "__main__":
    build()
