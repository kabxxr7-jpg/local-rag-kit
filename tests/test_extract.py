from __future__ import annotations

import pytest
from reportlab.pdfgen import canvas

from local_rag.errors import NoTextError
from local_rag.extract import extract_pdf

from .conftest import SAMPLES, SCENARIO_PDFS


def test_pages_are_numbered_from_one_and_carry_the_file_name():
    ex = extract_pdf(SAMPLES / "harbor-pine-handbook.pdf")
    assert ex.source == "harbor-pine-handbook.pdf" and ex.page_count == 4
    assert [p.page for p in ex.pages] == [1, 2, 3, 4]
    assert all(p.source == "harbor-pine-handbook.pdf" for p in ex.pages)


def test_each_fact_is_on_the_page_the_eval_says():
    ex = {p.page: p.text for p in extract_pdf(SAMPLES / "harbor-pine-handbook.pdf").pages}
    assert "25 days of paid annual leave" in ex[2]
    assert "Core hours are 10:00 to 15:00" in ex[1]
    assert "1,200 EUR" in ex[3]
    assert "Ines Carvalho" in ex[4]
    assert "25 days" not in ex[1]


def test_scanned_pdf_raises_a_clear_error_that_says_ocr_is_not_covered():
    with pytest.raises(NoTextError) as err:
        extract_pdf(SAMPLES / "scanned-notice.pdf")
    message = str(err.value)
    assert "scanned-notice.pdf" in message and "none has extractable text" in message and "does not do OCR" in message


def test_a_page_without_text_is_skipped_and_listed(tmp_path):
    path = tmp_path / "mixed.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(72, 700, "Page one has words in it.")
    c.showPage()
    c.showPage()  # page two is empty
    c.drawString(72, 700, "Page three has words too.")
    c.showPage()
    c.save()
    ex = extract_pdf(path)
    assert [p.page for p in ex.pages] == [1, 3]
    assert ex.empty_pages == [2] and ex.page_count == 3


def test_table_rows_stay_on_one_line_in_layout_mode():
    text = {p.page: p.text for p in extract_pdf(SAMPLES / "meridian-price-list.pdf", "layout").pages}[1]
    assert "Pro | 5 TB | 10 | 29 EUR" in text
    assert "Plan | Storage | Users | Price per month" in text


def test_plain_mode_flattens_a_table_into_one_cell_per_line():
    text = {p.page: p.text for p in extract_pdf(SAMPLES / "meridian-price-list.pdf", "plain").pages}[1]
    assert "Pro | 5 TB" not in text
    assert "Pro\n5 TB\n10\n29 EUR" in text


def test_columnwise_table_loses_its_rows_in_plain_mode_but_not_in_layout_mode():
    plain = extract_pdf(SCENARIO_PDFS / "price-list-columnwise.pdf", "plain").pages[0].text
    layout = extract_pdf(SCENARIO_PDFS / "price-list-columnwise.pdf", "layout").pages[0].text
    assert "Pro | 5 TB | 10 | 29 EUR" in layout
    assert "Pro\nBusiness" in plain and "29 EUR" in plain and "Pro | " not in plain


def test_two_columns_interleave_in_plain_and_layout_but_not_in_columns_mode():
    sentence = "Customers may return unused goods\nwithin 30 days of delivery for a full\nrefund."
    for mode in ("plain", "layout"):
        text = extract_pdf(SCENARIO_PDFS / "shop-policies-two-columns.pdf", mode).pages[0].text
        assert sentence not in text, mode
    columns = extract_pdf(SCENARIO_PDFS / "shop-policies-two-columns.pdf", "columns").pages[0].text
    assert sentence in columns
    assert columns.index("Returns policy") < columns.index("Delivery policy")
    assert "Standard delivery takes 3 to\n5 working days." in columns


def test_columns_mode_splits_at_the_middle_of_the_page_not_somewhere_else(tmp_path):
    path = tmp_path / "split.pdf"
    c = canvas.Canvas(str(path), pagesize=(600, 400))
    c.drawString(100, 200, "far left")
    c.drawString(240, 300, "just left of the middle")  # starts at 40 percent of the width
    c.drawString(360, 300, "just right of the middle")  # starts at 60 percent
    c.drawString(500, 200, "far right")
    c.save()
    text = extract_pdf(path, "columns").pages[0].text
    assert text == "just left of the middle\nfar left\n\njust right of the middle\nfar right"


def test_ligatures_and_hyphenation_are_repaired_by_extract():
    text = extract_pdf(SCENARIO_PDFS / "office-notes-ligatures.pdf").pages[0].text
    assert "first Monday of every month" in text and "office" in text and "staircase" in text and "cupboard" in text and "reception desk" in text
    assert "\ufb01" not in text and "-\n" not in text


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError, match="unknown extract mode"):
        extract_pdf(SAMPLES / "harbor-pine-handbook.pdf", "psychic")
