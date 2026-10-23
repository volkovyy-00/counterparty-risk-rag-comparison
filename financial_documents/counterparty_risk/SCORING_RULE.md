# Scoring rule

Fixed and committed **before** the final run. The demo shows this file's commit time and SHA
next to the run's timestamp. Code: `evaluate.py`, `verify.py`, `run_all.py`.

## Question

> What industry risks connect these counterparties, and which counterparties share each one?

Group `auto_semis`: GM, F, TSLA, APTV, BWA, LEA, NXPI, MCHP, ON, TXN. Each company's latest 10-K, Item 1A only.

## Rule

- **Same contract for every approach.** Each approach returns claims `{company, category, leaf, quote, source_ref}`.
- **Same verifier for every approach.** A claim counts only if its labels are in taxonomy v2 (checked in code, not by
  the provider) and its quote is found verbatim in **that company's own** Item 1A. Matching ignores typography and
  whitespace only. Quotes shorter than 20 characters are rejected.
- **Unit.** A (company, leaf) pair and a (company, category) pair claimed as an exposure.
- **Shared only.** The question asks about shared risks. The truth is the set of key pairs whose label is true for at
  least 2 companies. The prediction is the set of verified pairs whose label the approach claims for at least
  2 companies.
- **Precision, recall, F1** of the predicted pairs against the hand-labelled key (`ground_truth.yaml`), per approach,
  at both levels. No LLM judge.
- **Quote coverage.** Verified claims divided by all claims returned.
- **Rerun consistency.** The mean pairwise Jaccard of the predicted (company, leaf) pairs across 3 independent runs,
  with the cache off for runs 2 and 3.
- **Companies covered.** How many of the 10 companies appear in at least one shared, verified claim.
- **Tokens, cost and latency.** Build and ask are reported separately. Cost uses `pricing.yaml` at the date shown.
  Latency is the wall clock recorded live and is never taken from a replay.
- **Control (optional).** *Long context* sends all ten Item 1A sections in one call under the same contract. It
  runs only if the counted prompt fits the model's context window; otherwise it shows "n/a – N tokens".
- **Key status.** Until `ground_truth.yaml` has `status: verified`, every P/R/F1 shown carries
  "DRAFT KEY – not for slides".

## Not part of the score

Keyword mapping is used only as a fallback for claims that arrive with no label. The number of claims that fell back
is reported.
