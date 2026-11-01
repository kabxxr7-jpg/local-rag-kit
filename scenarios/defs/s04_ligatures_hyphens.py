"""Extraction garbage: ligature characters and words broken at the end of a line survive into the chunks."""
from __future__ import annotations

from framework import Edit, Scenario, cli

MARKER = "    # inherited cleaner: whitespace only\n"
ORIGINAL = (
    '    text = unicodedata.normalize("NFKC", text)\n'
    "    text = text.translate(_INVISIBLE)\n"
    '    text = _HYPHEN_BREAK.sub(r"\\1\\2", text)\n'
)
BREAK = Edit("local_rag/clean.py", ORIGINAL, MARKER)

QUESTION = "When does the fire drill take place?"


def check(ctx):
    page = ctx.norm(ctx.page_text("office-notes-ligatures.pdf", 1))
    with ctx.step("the stored text has no ligature characters"):
        bad = sorted({c for c in page if 0xFB00 <= ord(c) <= 0xFB06})
        assert not bad, "stored text still contains " + ", ".join(f"U+{ord(c):04X}" for c in bad) + f" (for example: {page[page.find(bad[0]) - 6 : page.find(bad[0]) + 12]!r})"
    with ctx.step("words broken at the end of a line are joined (staircase, cupboard, reception)"):
        missing = [w for w in ("staircase", "cupboard", "reception desk") if w not in page]
        assert not missing, f"not found in the stored text: {missing}"
    with ctx.step("the fire drill sentence can be found as written"):
        assert "The fire drill takes place on the first Monday of every month" in page, "the sentence is not in the stored text"
    with ctx.step("the word 'office' in the heading is a word again"):
        assert "Safety notes for the office" in page


SCENARIO = Scenario(
    name="extraction-ligatures-hyphens",
    title="PDF text garbage: ligatures and line-end hyphens",
    story=(
        "The PDF was typeset with ligature glyphs (fi, fl) and hyphenates words at the end of a line. pypdf hands them over faithfully: 'first' with the fi ligature U+FB01 is one "
        "character, 'stair-' and 'case' are two lines. The inherited cleaner only collapses whitespace, so the garbage is embedded, stored and quoted."
    ),
    pdfs=["office-notes-ligatures.pdf"],
    setup=[cli("ingest", "pdfs")],
    break_=[BREAK, cli("ingest", "--rebuild", "pdfs")],
    symptom=[cli("ask", "--debug", "--show-prompt", QUESTION)],
    diagnose=[cli("doctor", "pdfs")],
    check=check,
    fixes={
        "restore_the_cleaner_and_rebuild": [Edit("local_rag/clean.py", MARKER, ORIGINAL), cli("ingest", "--rebuild", "pdfs")],
    },
    wrongs={
        "normalise_but_do_not_dehyphenate": [Edit("local_rag/clean.py", MARKER, '    text = unicodedata.normalize("NFKC", text)\n'), cli("ingest", "--rebuild", "pdfs")],
        "dehyphenate_but_keep_ligatures": [Edit("local_rag/clean.py", MARKER, '    text = _HYPHEN_BREAK.sub(r"\\1\\2", text)\n'), cli("ingest", "--rebuild", "pdfs")],
        "strip_non_ascii": [Edit("local_rag/clean.py", MARKER, '    text = re.sub(r"[^\\x00-\\x7f]", "", text)\n'), cli("ingest", "--rebuild", "pdfs")],
        "fix_the_code_but_do_not_rebuild": [Edit("local_rag/clean.py", MARKER, ORIGINAL)],
    },
    fix_notes={"restore_the_cleaner_and_rebuild": "NFKC turns the ligature characters into letters, soft hyphens vanish, a hyphen before a line break followed by a lower case letter is joined. The rebuild matters: the PDF did not change, so a plain `ingest` skips it."},
    wrong_notes={
        "normalise_but_do_not_dehyphenate": "The ligatures are gone, 'stair- case' is still two words.",
        "dehyphenate_but_keep_ligatures": "'staircase' is whole, the first/fire ligature is still one odd character, so 'first Monday' cannot be found.",
        "strip_non_ascii": "Deletes the ligature characters instead of converting them: 'office' becomes 'ofce', 'first' becomes 'rst'.",
        "fix_the_code_but_do_not_rebuild": "The store still holds the old text: the file is unchanged, so nothing is re-read until `--rebuild`.",
    },
    observe=[cli("ask", QUESTION)],
)
