from __future__ import annotations

from local_rag.clean import clean_text


def test_ligature_characters_become_letters():
    assert clean_text("the \ufb01rst o\ufb03ce and a \ufb02oor") == "the first office and a floor"


def test_hyphenated_line_break_is_joined_when_next_line_is_lower_case():
    assert clean_text("the stair-\ncase and the cup-\n  board") == "the staircase and the cupboard"


def test_hyphen_before_a_capital_or_digit_is_kept():
    assert clean_text("Harbor-\nPine and 2026-\n2027") == "Harbor-\nPine and 2026-\n2027"


def test_a_hyphen_inside_a_line_is_untouched():
    assert clean_text("a first-aid kit, 14-day trial") == "a first-aid kit, 14-day trial"


def test_soft_hyphen_and_zero_width_characters_are_removed():
    assert clean_text("co\u00adop\u200bera\u2060tion\ufeff") == "cooperation"


def test_wide_gap_becomes_a_column_bar_and_single_spaces_stay():
    assert clean_text("Pro          5 TB     10      29 EUR") == "Pro | 5 TB | 10 | 29 EUR"
    assert clean_text("two  spaces stay two? no: one") == "two spaces stay two? no: one"


def test_runs_of_spaces_tabs_and_nbsp_collapse():
    assert clean_text("a \tb\u00a0c") == "a b c"
    assert clean_text("a \t b") == "a | b"  # three blanks in a row are a column gap, whatever they are made of


def test_blank_lines_collapse_to_one_and_ends_are_stripped():
    assert clean_text("\n\n  a\n\n\n\n\nb  \n\n") == "a\n\nb"


def test_three_and_four_newlines_already_collapse_to_one_blank_line():
    assert clean_text("a\nb") == "a\nb"
    assert clean_text("a\n\nb") == "a\n\nb"
    assert clean_text("a\n\n\nb") == "a\n\nb"
    assert clean_text("a\n\n\n\nb") == "a\n\nb"


def test_windows_and_old_mac_line_endings():
    assert clean_text("a\r\nb\rc") == "a\nb\nc"


def test_lines_are_stripped_but_not_merged():
    assert clean_text("  first line  \n   second line") == "first line\nsecond line"


def test_empty_stays_empty():
    assert clean_text("") == "" and clean_text(" \n \t ") == ""
