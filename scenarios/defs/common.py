"""Probe questions shared by several scenarios: (question, file, page, a phrase that sits inside one sentence of that page)."""
from __future__ import annotations

MAIN_PDFS = ["harbor-pine-handbook.pdf", "aurora-kettle-manual.pdf", "meridian-price-list.pdf"]

PROBES = [
    ("How many days of paid annual leave does each employee get per year?", "harbor-pine-handbook.pdf", 2, "25 days of paid annual leave"),
    ("What is the maximum fill level of the Aurora AK-200?", "aurora-kettle-manual.pdf", 1, "maximum fill level is 1.7 litres"),
    ("How much does the Pro plan cost per month?", "meridian-price-list.pdf", 1, "Pro | 5 TB | 10 | 29 EUR"),
    ("What is the code for ordering a spare limescale filter?", "aurora-kettle-manual.pdf", 4, "code AF-20"),
    ("In which countries are the data centres located?", "meridian-price-list.pdf", 3, "Finland and Ireland"),
    ("Who is the trust person for raising harassment concerns?", "harbor-pine-handbook.pdf", 4, "Ines Carvalho"),
]
