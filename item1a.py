"""Turn a 10-K HTML document into text and cut out Item 1A (Risk Factors)."""
import re

from bs4 import BeautifulSoup

BLOCK_TAGS = ["p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section"]

_SEP = r"[ \t.:\-–—]*"
START = re.compile(rf"(?im)^[ \t]*item[ \t]*1a\b{_SEP}(?:risk[ \t]+factors)?[ \t.]*$")
END = re.compile(rf"(?im)^[ \t]*item[ \t]*(?:1b|1c|2)\b{_SEP}"
                 r"(?:unresolved[ \t]+staff[ \t]+comments|cybersecurity|properties)?[ \t.]*$")
# Fallback for documents whose headings are not on their own line.
START_LOOSE = re.compile(rf"(?i)item\s*1a\b{_SEP}\s*risk\s+factors")
END_LOOSE = re.compile(rf"(?i)item\s*(?:1b|1c|2)\b{_SEP}\s*(?:unresolved|cybersecurity|properties)")

SMALLER_REPORTING = re.compile(r"(?i)smaller reporting compan(y|ies).{0,200}not required to provide")


def html_to_text(html):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "ix:header"]):
        tag.decompose()
    for tag in soup.find_all(style=re.compile(r"display:\s*none", re.I)):
        tag.decompose()
    for tag in soup.find_all(BLOCK_TAGS):
        tag.append("\n")
    for tag in soup.find_all("td"):
        tag.append(" ")
    text = soup.get_text("").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _longest_span(text, start_re, end_re):
    best = None
    for s in start_re.finditer(text):
        e = end_re.search(text, s.end())
        if e and (best is None or e.start() - s.end() > best[1] - best[0]):
            best = (s.end(), e.start())
    return best


def extract_item1a(text):
    """Return (item1a_text, method). The longest heading-to-heading span wins,
    which skips the table-of-contents entry. method is 'heading', 'loose' or 'not_found'."""
    span = _longest_span(text, START, END)
    method = "heading"
    if span is None or span[1] - span[0] < 2000:
        loose = _longest_span(text, START_LOOSE, END_LOOSE)
        if loose and (span is None or loose[1] - loose[0] > span[1] - span[0]):
            span, method = loose, "loose"
    if span is None:
        return "", "not_found"
    body = text[span[0]:span[1]].strip()
    body = re.sub(r"(?i)^risk factors\s*", "", body)  # heading split over two lines
    return body, method
