"""Generates the fictional sample PDFs (deterministic: the same bytes every time) with reportlab.

    python samples/make_pdfs.py            writes samples/pdfs/*.pdf and scenarios/pdfs/*.pdf

Everything in them is made up: the studio, the kettle, the cloud storage company, the prices and the rules.
The facts in these files are what tests/ and eval/questions.json check against.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

W, H = A4
MARGIN = 56


def _canvas(path: Path, title: str) -> canvas.Canvas:
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1, pageCompression=0)
    c.setTitle(title)
    c.setAuthor("fictional sample")
    return c


def _header(c: canvas.Canvas, doc_title: str, page: int, pages: int, font: str = "Helvetica") -> None:
    c.setFont(font, 8)
    c.drawString(MARGIN, H - 32, doc_title)
    c.drawRightString(W - MARGIN, 28, f"Page {page} of {pages}")


def _paragraphs(c, y: float, blocks: list[tuple[str, str]], x: float = MARGIN, width: float = W - 2 * MARGIN, font: str = "Helvetica") -> float:
    """blocks: ("h", text) is a heading, ("p", text) a paragraph, ("b", text) a bullet. Returns the next free y."""
    for kind, text in blocks:
        if kind == "h":
            y -= 10
            c.setFont(font + ("-Bold" if font == "Helvetica" else ""), 14)
            c.drawString(x, y, text)
            y -= 20
            continue
        size, leading, indent = 10.5, 15, (14 if kind == "b" else 0)
        c.setFont(font, size)
        lines = simpleSplit(text, font, size, width - indent)
        for n, line in enumerate(lines):
            if kind == "b" and n == 0:
                c.drawString(x, y, "-")
            c.drawString(x + indent, y, line)
            y -= leading
        y -= 6
    return y


# ---------------------------------------------------------------------------------------------------------------------
# the three sample documents
# ---------------------------------------------------------------------------------------------------------------------
HANDBOOK = [
    (
        "Working hours and place of work",
        [
            ("p", "Harbor & Pine Studio is a small design studio based in Porto. This handbook describes the rules every member of staff works under. It is reviewed once a year and the version in this file applies from 1 January 2026."),
            ("h", "1. Working hours"),
            ("p", "The standard working week is 36 hours. Core hours are 10:00 to 15:00 Central European Time: everyone is reachable and available for calls during that window. Outside core hours people organise their own time, as long as the weekly hours add up."),
            ("p", "The studio is open from 08:00 to 19:00 on weekdays. There are no meetings on Wednesdays, so that the day can be used for focused work."),
            ("h", "2. Remote work"),
            ("p", "Staff may work remotely up to three days per week. The two days in the studio are agreed in the team calendar at the start of each quarter. Working from another country for more than 10 days in a year needs written approval from the managing partner."),
            ("h", "3. Devices and security"),
            ("p", "Every laptop uses full-disk encryption and must lock itself after 5 minutes without activity. A password manager is mandatory for all work accounts, and a lost device must be reported to the office manager on the same day."),
        ],
    ),
    (
        "Leave and absence",
        [
            ("h", "4. Annual leave"),
            ("p", "Every employee has 25 days of paid annual leave per calendar year, in addition to public holidays. Up to 5 unused days may be carried over and must be taken by 31 March of the following year; anything left after that date expires."),
            ("p", "A leave request of more than 5 consecutive working days needs at least 4 weeks' notice. Shorter requests only need the agreement of the team lead."),
            ("h", "5. Sick leave"),
            ("p", "The first 3 days of an illness do not need a doctor's note. From the fourth day a medical certificate is required. Sick leave is paid in full for up to 20 days per calendar year."),
            ("h", "6. Parental leave"),
            ("p", "The primary carer receives 18 weeks of parental leave at full pay. The other parent receives 6 weeks at full pay. Both periods can be taken in parts within the first two years of the child's life."),
        ],
    ),
    (
        "Expenses, equipment and learning",
        [
            ("h", "7. Expense claims"),
            ("p", "Expense claims must be submitted within 30 days of the purchase, using the expenses form on the intranet. Approved claims are paid with the next payroll run. A receipt photo is required for every item above 25 EUR."),
            ("h", "8. Travel"),
            ("p", "When travelling for work, meals are reimbursed up to 45 EUR per day and hotels up to 140 EUR per night. Train travel is preferred for journeys under 6 hours; flights in economy class are reimbursed in full."),
            ("h", "9. Equipment and learning"),
            ("p", "Each employee has an equipment budget of 1,200 EUR every three years for a laptop, plus a one-time monitor allowance of 250 EUR. The learning budget is 800 EUR per person per year for courses, books and conferences; it does not roll over to the next year."),
        ],
    ),
    (
        "Onboarding, feedback and conduct",
        [
            ("h", "10. Onboarding and probation"),
            ("p", "Every new employee is paired with a buddy for the first 6 weeks. The probation period lasts 3 months; during probation either side may end the contract with 1 week of notice. After probation the notice period is 2 months."),
            ("h", "11. Feedback and salary"),
            ("p", "Performance reviews take place twice a year, in May and in November. Salaries are reviewed once a year, in January, together with the budget for the new year."),
            ("h", "12. Conduct"),
            ("p", "Gifts from clients worth more than 50 EUR must be declared to the managing partner. Concerns about harassment can be raised in confidence with the trust person, Ines Carvalho, or with the managing partner. Client files are kept for 7 years and then deleted."),
        ],
    ),
]

KETTLE = [
    (
        "Safety and first use",
        [
            ("p", "Aurora AK-200 smart kettle. Please read this manual before first use and keep it for later. The Aurora AK-200 is a household appliance and is not meant for commercial use."),
            ("h", "Safety"),
            ("b", "The maximum fill level is 1.7 litres. The minimum fill level is 0.5 litres, marked by the lower line inside the kettle."),
            ("b", "Never switch the kettle on without water. If it runs dry, the dry-boil protection switches it off and the display shows E1."),
            ("b", "Place the kettle on a flat, dry surface. Never immerse the power base in water."),
            ("b", "The kettle is rated 2200 W at 230 V."),
            ("h", "First use"),
            ("p", "Before the first use, fill the kettle to the maximum level, boil the water and pour it away. Repeat this twice to rinse out any production residue."),
        ],
    ),
    (
        "Operation",
        [
            ("h", "Temperature presets"),
            ("p", "Press the preset button to cycle through the five temperature presets: 70 degrees for baby milk, 80 degrees for green tea, 90 degrees for coffee, 95 degrees for black tea and 100 degrees for boiling."),
            ("h", "Keep-warm function"),
            ("p", "Press and hold the start button for 2 seconds to switch on the keep-warm function. The kettle holds the selected temperature for 30 minutes and then switches itself off."),
            ("h", "Child lock"),
            ("p", "To lock the controls, hold the preset button for 3 seconds until the lock symbol lights up. Repeat to unlock. The lid is opened with the release button on the handle."),
        ],
    ),
    (
        "Care and troubleshooting",
        [
            ("h", "Descaling"),
            ("p", "Descale the kettle every 4 weeks, or sooner when the ring light blinks amber. Fill it with one part white vinegar and two parts water, bring it to the boil, let it stand for 15 minutes, then rinse it well twice."),
            ("h", "Error codes"),
            ("b", "E1: dry-boil protection has switched the kettle off. Let it cool and add water."),
            ("b", "E3: the temperature sensor has failed. Do not use the kettle and contact customer service."),
            ("h", "Reset and warranty"),
            ("p", "To reset the kettle, unplug it from the mains for 30 seconds and plug it in again. The Aurora AK-200 has a warranty of 2 years from the date of purchase; the receipt is needed for a claim."),
        ],
    ),
    (
        "Specifications and disposal",
        [
            ("h", "Specifications"),
            ("b", "Height 24 cm, weight 1.2 kg. The mains cable is 0.75 m long and can be stored in the base."),
            ("b", "The body is brushed stainless steel; the lid is made of BPA-free plastic."),
            ("b", "One litre of water reaches the boil in about 3 minutes."),
            ("h", "Limescale filter"),
            ("p", "The spout has a removable limescale filter. Rinse it under the tap once a week. A spare filter can be ordered with the code AF-20."),
            ("h", "Disposal"),
            ("p", "Do not throw the kettle away with household waste. Take it to a collection point for electrical and electronic equipment."),
        ],
    ),
]


def _table(c, y: float, header: list[str], rows: list[list[str]], col_x: list[float], font: str = "Helvetica", row_h: float = 20, col_wise: bool = False) -> float:
    """Draw a grid. ``col_wise`` writes the cells column by column (header, then every row of the first column, ...), which is how
    some PDF producers lay the content stream out: a text extractor that follows the stream then reads columns, not rows."""
    top = y
    n_rows = len(rows) + 1
    c.setLineWidth(0.5)
    for r in range(n_rows + 1):
        c.line(col_x[0] - 6, top - r * row_h + 5, col_x[-1] + 110, top - r * row_h + 5)
    cells = [header] + rows
    order = (
        [(r, k) for k in range(len(header)) for r in range(n_rows)]
        if col_wise
        else [(r, k) for r in range(n_rows) for k in range(len(header))]
    )
    for r, k in order:
        c.setFont(font + ("-Bold" if r == 0 else ""), 10)
        c.drawString(col_x[k], top - r * row_h - 10, cells[r][k])
    return top - n_rows * row_h - 12


PLANS_HEADER = ["Plan", "Storage", "Users", "Price per month"]
PLANS = [
    ["Starter", "100 GB", "1", "4 EUR"],
    ["Plus", "1 TB", "3", "12 EUR"],
    ["Pro", "5 TB", "10", "29 EUR"],
    ["Business", "20 TB", "50", "89 EUR"],
]
ADDONS_HEADER = ["Add-on", "Unit", "Price per month"]
ADDONS = [
    ["Extra storage", "per 1 TB", "6 EUR"],
    ["Priority support", "per account", "15 EUR"],
    ["Extended file history (365 days)", "per account", "9 EUR"],
]


def make_handbook(path: Path) -> None:
    c = _canvas(path, "Harbor & Pine Studio staff handbook (fictional)")
    for n, (title, blocks) in enumerate(HANDBOOK, start=1):
        _header(c, "Harbor & Pine Studio - Staff handbook 2026", n, len(HANDBOOK))
        c.setFont("Helvetica-Bold", 20)
        c.drawString(MARGIN, H - 80, title)
        _paragraphs(c, H - 112, blocks)
        c.showPage()
    c.save()


def make_kettle(path: Path) -> None:
    c = _canvas(path, "Aurora AK-200 smart kettle manual (fictional)")
    for n, (title, blocks) in enumerate(KETTLE, start=1):
        _header(c, "Aurora AK-200 smart kettle - user manual", n, len(KETTLE))
        c.setFont("Helvetica-Bold", 20)
        c.drawString(MARGIN, H - 80, title)
        _paragraphs(c, H - 112, blocks)
        c.showPage()
    c.save()


def make_price_list(path: Path, col_wise: bool = False, title: str = "Meridian Cloud Storage price list 2026 (fictional)") -> None:
    c = _canvas(path, title)
    col_x = [MARGIN, MARGIN + 130, MARGIN + 230, MARGIN + 330]
    # page 1
    _header(c, "Meridian Cloud Storage - Price list 2026", 1, 3)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(MARGIN, H - 80, "Plans")
    y = _paragraphs(c, H - 108, [("p", "Meridian Cloud Storage offers four plans. All plans include end-to-end encryption and a 14-day free trial. Paying for a full year in advance gives a 15 percent discount on the monthly prices below.")])
    y = _table(c, y - 6, PLANS_HEADER, PLANS, col_x, col_wise=col_wise)
    _paragraphs(c, y - 6, [("p", "The Business plan includes a dedicated account manager. Prices are per month and exclude VAT.")])
    c.showPage()
    # page 2
    _header(c, "Meridian Cloud Storage - Price list 2026", 2, 3)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(MARGIN, H - 80, "Add-ons and terms")
    y = _table(c, H - 108, ADDONS_HEADER, ADDONS, [MARGIN, MARGIN + 220, MARGIN + 330], col_wise=col_wise)
    _paragraphs(
        c,
        y - 6,
        [
            ("h", "Terms"),
            ("p", "A cancellation takes effect at the end of the current billing period. Refunds are pro-rata and only possible within 10 days of a payment. Education customers get 40 percent off the Plus plan."),
        ],
    )
    c.showPage()
    # page 3
    _header(c, "Meridian Cloud Storage - Price list 2026", 3, 3)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(MARGIN, H - 80, "Data, uptime and support")
    _paragraphs(
        c,
        H - 108,
        [
            ("h", "Where your data lives"),
            ("p", "Files are stored in data centres in Finland and Ireland and are copied to three locations. The largest single file that can be uploaded is 50 GB. Deleted files stay in the bin for 30 days before they are removed for good."),
            ("h", "Uptime promise"),
            ("p", "Meridian aims for 99.9 percent availability per month. If the monthly uptime falls below 99.9 percent, customers receive a service credit of 10 percent of that month's fee."),
            ("h", "Support hours"),
            ("p", "Standard support answers e-mail from Monday to Friday, 09:00 to 17:00 UTC. The priority support add-on also covers weekends and answers within 4 hours."),
        ],
    )
    c.showPage()
    c.save()


def make_scanned_notice(path: Path) -> None:
    """One page that is a picture of text and has no text layer at all (what a scanner produces)."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("L", (900, 360), 255)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=34)
    draw.text((30, 40), "NOTICE TO ALL STAFF", fill=0, font=font)
    draw.text((30, 110), "The warehouse closes on 12 December", fill=0, font=font)
    draw.text((30, 170), "for the annual stock count.", fill=0, font=font)
    c = _canvas(path, "Scanned notice (fictional, image only)")
    c.drawImage(ImageReader(img), MARGIN, H - 300, width=480, height=192)
    c.showPage()
    c.save()


# ---------------------------------------------------------------------------------------------------------------------
# scenario documents (each reproduces one real extraction problem)
# ---------------------------------------------------------------------------------------------------------------------
LEFT_COLUMN = [
    "Returns policy",
    "Customers may return unused goods",
    "within 30 days of delivery for a full",
    "refund. The goods must be in their",
    "original packaging. Returns are free",
    "of charge inside the country.",
    "A refund is paid to the original",
    "payment method within 5 working",
    "days after the parcel arrives.",
]
RIGHT_COLUMN = [
    "Delivery policy",
    "Orders above 50 EUR ship free of",
    "charge. Standard delivery takes 3 to",
    "5 working days. Express delivery",
    "takes 1 working day and costs 9 EUR.",
    "We do not deliver to post office",
    "boxes. Parcels are left with a",
    "neighbour only if you allow it in",
    "your account settings.",
]


def make_two_columns(path: Path) -> None:
    """Two text columns, written row by row (left line 1, right line 1, left line 2, ...): reading the content stream in
    order interleaves the columns, which is the classic 'two columns merged' extraction."""
    c = _canvas(path, "Shop policies, two columns (fictional)")
    _header(c, "Corner Shop policies", 1, 1)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(MARGIN, H - 80, "Shop policies")
    c.setFont("Helvetica", 10.5)
    y = H - 120
    for left, right in zip(LEFT_COLUMN, RIGHT_COLUMN):
        c.drawString(MARGIN, y, left)
        c.drawString(W / 2 + 12, y, right)
        y -= 16
    c.showPage()
    c.save()


def make_ligatures(path: Path) -> None:
    """Text with ligature characters (U+FB01, U+FB02) and words hyphenated at the end of a line, in an embedded TrueType font."""
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont("VeraLig", os.path.join(os.path.dirname(reportlab.__file__), "fonts", "Vera.ttf")))
    lines = [
        "Safety notes for the of\ufb01ce",
        "",
        "The \ufb01re drill takes place on the \ufb01rst Monday of every month at 11:15.",
        "Staff must leave their \ufb02oor by the nearest stair-",
        "case and meet at the car park behind the building.",
        "The \ufb01rst-aid kit is kept in the kitchen cup-",
        "board above the sink, and the defibrillator is at the recep-",
        "tion desk. A \ufb01re warden is named on every \ufb02oor plan.",
    ]
    c = _canvas(path, "Office safety notes with ligatures (fictional)")
    c.setFont("VeraLig", 11)
    y = H - 100
    for line in lines:
        c.drawString(MARGIN, y, line)
        y -= 18
    c.showPage()
    c.save()


def build_all(root: Path) -> list[Path]:
    main = root / "samples" / "pdfs"
    scen = root / "scenarios" / "pdfs"
    main.mkdir(parents=True, exist_ok=True)
    scen.mkdir(parents=True, exist_ok=True)
    out = [
        (main / "harbor-pine-handbook.pdf", make_handbook),
        (main / "aurora-kettle-manual.pdf", make_kettle),
        (main / "meridian-price-list.pdf", make_price_list),
        (main / "scanned-notice.pdf", make_scanned_notice),
        (scen / "shop-policies-two-columns.pdf", make_two_columns),
        (scen / "office-notes-ligatures.pdf", make_ligatures),
        (scen / "price-list-columnwise.pdf", lambda p: make_price_list(p, col_wise=True)),
    ]
    for path, fn in out:
        fn(path)
    return [p for p, _ in out]


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    for p in build_all(root):
        print(f"wrote {p.relative_to(root)} ({p.stat().st_size} bytes)")
    sys.exit(0)
