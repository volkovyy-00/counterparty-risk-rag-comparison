"""The shared checks every claim passes through, whatever approach produced it.

1. validate_label : company in the group; category and leaf in the closed taxonomy
                    lists; leaf belongs to the category. This is the code's own check
                    and does not rely on the provider enforcing a JSON-schema enum.
2. verify_quote   : the quote occurs verbatim (typography-tolerant) in THAT company's
                    Item 1A; the character offsets are stored for highlighting.

Keyword fallback: a claim that arrives with no taxonomy label at all (e.g. a
model that answers in free text) is mapped onto a leaf by the keyword lists in
taxonomy.yaml and flagged `fallback`. A claim WITH a label that is not in the
taxonomy is rejected, never re-mapped. A claim an approach already marked with
`label_error` (approach 3's one-label rules) is rejected as a label, with that reason.
`driver` and `secondary` pass through unchanged; nothing downstream scores them.
"""
import re
import unicodedata

import taxonomy

MIN_QUOTE_CHARS = 20

_TYPOGRAPHY = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                             " ": " ", "•": " ", "­": ""})


def _norm_char(ch):
    return unicodedata.normalize("NFKC", ch).translate(_TYPOGRAPHY)


def normalise_with_map(text):
    """Normalised text plus, for each normalised character, its index in the raw text."""
    out, index = [], []
    for i, ch in enumerate(text):
        for n in _norm_char(ch):
            if n.isspace():
                if not out or out[-1] == " ":
                    continue
                n = " "
            out.append(n)
            index.append(i)
    while out and out[-1] == " ":
        out.pop()
        index.pop()
    return "".join(out), index


def normalise(text):
    return normalise_with_map(text)[0].strip()


def locate(quote, text):
    """(start, end) of `quote` in raw `text`, or None. Matching ignores typography and whitespace."""
    q = normalise(quote)
    if len(q) < MIN_QUOTE_CHARS:
        return None
    norm, index = normalise_with_map(text)
    i = norm.find(q)
    if i < 0:
        return None
    return index[i], index[i + len(q) - 1] + 1


def closest_sentence(quote, text):
    """Best fuzzy-matching sentence in `text` (for showing why a quote was rejected)."""
    from rapidfuzz import fuzz, process

    sentences = [s for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text)) if len(s) > 30]
    if not sentences:
        return None, 0.0
    match, score, _ = process.extractOne(normalise(quote), sentences, scorer=fuzz.ratio)
    return match, round(score / 100, 3)


def validate_label(claim, tickers):
    """Return None if the label is valid, else the reason for rejection."""
    if claim.get("company") not in tickers:
        return f"company '{claim.get('company')}' is not in the group"
    cat, leaf = claim.get("category"), claim.get("leaf")
    if cat not in taxonomy.CATEGORY_IDS:
        return f"category '{cat}' is not in taxonomy v{taxonomy.VERSION}"
    if leaf not in taxonomy.LEAVES:
        return f"leaf '{leaf}' is not in taxonomy v{taxonomy.VERSION}"
    if taxonomy.category_of(leaf) != cat:
        return f"leaf '{leaf}' does not belong to category '{cat}'"
    return None


def verify_claims(claims, filings, sources=None):
    """Check every claim; return (accepted, rejected, stats). Never modifies the input claims.

    filings : list of filing dicts (ticker, text, ...) - the group's Item 1A sections
    sources : optional {source_ref: text} - the excerpts the approach showed the model
    """
    sources = sources or {}
    by_ticker = {f["ticker"]: f for f in filings}
    accepted, rejected, fallbacks = [], [], 0
    for raw in claims:
        claim = {k: raw.get(k, "") for k in ("company", "category", "leaf", "quote", "source_ref", "risk", "driver")}
        claim.update(secondary=bool(raw.get("secondary")), fallback=False)  # driver, secondary: shown, never scored
        if not claim["category"] and not claim["leaf"]:  # unlabelled: keyword fallback
            guess = taxonomy.leaves_for(f"{claim['risk']} {claim['quote']}")
            if guess:
                claim.update(leaf=guess[0], category=taxonomy.category_of(guess[0]), fallback=True)
                fallbacks += 1
        reason = raw.get("label_error") or validate_label(claim, by_ticker)  # label_error: an approach's own rule
        if reason:
            rejected.append(dict(claim, reason=reason, check="label"))
            continue
        span = locate(claim["quote"], by_ticker[claim["company"]]["text"])
        if span is None:
            other = next((t for t, f in by_ticker.items() if t != claim["company"] and locate(claim["quote"], f["text"])),
                         None)
            reason = (f"quote is from {other}'s filing, not {claim['company']}'s" if other
                      else "quote not found verbatim in the company's Item 1A")
            if len(normalise(claim["quote"])) < MIN_QUOTE_CHARS:
                reason = f"quote shorter than {MIN_QUOTE_CHARS} characters"
            rejected.append(dict(claim, reason=reason, check="quote"))
            continue
        src = sources.get(claim["source_ref"])
        claim.update(start=span[0], end=span[1],
                     in_cited_source=bool(src and locate(claim["quote"], src)) if sources else None)
        accepted.append(claim)
    total = len(accepted) + len(rejected)
    stats = {"claims": total, "accepted": len(accepted), "rejected": len(rejected),
             "rejected_label": sum(r["check"] == "label" for r in rejected),
             "rejected_quote": sum(r["check"] == "quote" for r in rejected),
             "keyword_fallback": fallbacks,
             "quote_coverage": round(len(accepted) / total, 3) if total else None,
             "not_in_cited_source": sum(c.get("in_cited_source") is False for c in accepted)}
    return accepted, rejected, stats


def dedupe(claims):
    """One claim per (company, leaf, quote) - repeated identical claims add nothing."""
    seen, out = set(), []
    for c in claims:
        key = (c["company"], c["leaf"], normalise(c["quote"]))
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def edgar_fragment_url(url, quote):
    """Primary-document URL with a #:~:text= fragment so the browser scrolls to the quote."""
    from urllib.parse import quote as q

    words = normalise(quote).split()
    if not url.startswith("http") or len(words) < 4:
        return url
    if len(words) <= 10:
        return f"{url}#:~:text={q(' '.join(words), safe='')}"
    return f"{url}#:~:text={q(' '.join(words[:5]), safe='')},{q(' '.join(words[-5:]), safe='')}"

