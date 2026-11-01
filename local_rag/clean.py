"""Text cleaning applied to each page after extraction and before chunking."""
from __future__ import annotations

import re
import unicodedata

# soft hyphen, zero width space / non-joiner / joiner, word joiner, byte order mark
_INVISIBLE = dict.fromkeys([0x00AD, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF], None)
_HYPHEN_BREAK = re.compile(r"([A-Za-z])-[ \t]*\n[ \t]*([a-z])")
_SPACES = re.compile(r"[ \t]+")
_WIDE_GAP = re.compile(r"[ \t]{3,}")
_BLANKS = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Normalise one page of extracted text.

    * NFKC turns ligature characters (U+FB01 and friends), non-breaking spaces and other compatibility forms into plain ones.
    * Soft hyphens and zero width characters are removed.
    * A word broken over two lines with a hyphen ("pro-" newline "cessing") is joined when the next line starts with a
      lower case letter. A real compound that happens to break at its hyphen ("twenty-" newline "four") is joined too:
      no rule can tell the two apart, and the README lists this as a known limit.
    * Inside a line, a gap of three or more spaces (what the "layout" extraction leaves between table columns) becomes " | ",
      so a table row stays one readable line: "Pro | 5 TB | 10 | 29 EUR".
    * Runs of spaces become one space; three or more newlines become two.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_INVISIBLE)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = "\n".join(_SPACES.sub(" ", _WIDE_GAP.sub(" | ", line.strip())) for line in text.split("\n"))
    text = _BLANKS.sub("\n\n", text)
    return text.strip()
