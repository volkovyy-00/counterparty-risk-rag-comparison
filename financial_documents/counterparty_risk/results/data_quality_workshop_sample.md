# Data quality - workshop sample (Company_Filings.csv + form10k-sample PDFs)

Source: the Apache-2.0 Neo4j genai-workshop `financial_documents/data`. The corpus built from it keeps the CSV labels unchanged, so a ticker can point at another company's filing.

**7 errors, 32 warnings, 4 notes.** Nothing below was corrected automatically.

| Severity | Check | Subject | Detail |
|---|---|---|---|
| ERROR | document_identity | APPLE INC (row ticker AAPL) | 'Apple' never appears in the first pages; document opens: "Section: Item1 >ITEM 1. BUSINESS Corporate History Verde Bio Holdings, Inc. was incorporated in the State of Nevada on February 24, 2010. On May 1, 2010, the Co..." |
| ERROR | duplicate_company | APPLE INC | 2 rows, CIKs ['1490054', '320193'], tickers ['AAPL', 'INTC'] |
| ERROR | file_missing | AMERICAN INTL GROUP (row ticker AIG) | 00005272-23-000007.pdf is referenced but not in form10k-sample/ |
| ERROR | file_missing | INTEL CORP (row ticker INTL) | 000050863-23-000006.pdf is referenced but not in form10k-sample/ |
| ERROR | file_missing | MCDONALDS CORP (row ticker MCD) | 000063908-23-000012.pdf is referenced but not in form10k-sample/ |
| ERROR | ticker_mismatch | APPLE INC (row ticker INTC) | Asset_Manager_Holdings.csv lists APPLE INC as ['AAPL'] |
| ERROR | ticker_mismatch | INTEL CORP (row ticker INTL) | Asset_Manager_Holdings.csv lists INTEL CORP as ['INTC'] |
| WARN | accession_format | AMERICAN INTL GROUP (row ticker AIG) | file name '00005272-23-000007' is not a valid accession number (expected 10-2-6 digits) |
| WARN | accession_format | INTEL CORP (row ticker INTL) | file name '000050863-23-000006' is not a valid accession number (expected 10-2-6 digits) |
| WARN | accession_format | MCDONALDS CORP (row ticker MCD) | file name '000063908-23-000012' is not a valid accession number (expected 10-2-6 digits) |
| WARN | cusip6_mismatch | AMERICAN INTL GROUP (row ticker AIG) | cusip6 '268748' is not the first 6 characters of '026874784' |
| WARN | cusip6_mismatch | APPLE INC (row ticker AAPL) | cusip6 '378331' is not the first 6 characters of '003783310' |
| WARN | cusip6_mismatch | APPLE INC (row ticker INTC) | cusip6 '378339' is not the first 6 characters of '037833950' |
| WARN | cusip6_mismatch | PAYPAL (row ticker PYPL) | cusip6 '163917' is not the first 6 characters of '001633917' |
| WARN | cusip_check_digit | APPLE INC (row ticker AAPL) | '003783310' fails the CUSIP check digit |
| WARN | cusip_check_digit | APPLE INC (row ticker INTC) | '037833950' fails the CUSIP check digit |
| WARN | cusip_check_digit | INTEL CORP (row ticker INTL) | '458140950' fails the CUSIP check digit |
| WARN | cusip_check_digit | MICROSOFT CORP (row ticker MSFT) | '594918954' fails the CUSIP check digit |
| WARN | cusip_check_digit | PAYPAL (row ticker PYPL) | '001633917' fails the CUSIP check digit |
| WARN | cusip_conflict | APPLE INC (row ticker AAPL) | cusip 3783310 vs holdings file ['037833100'] |
| WARN | cusip_conflict | APPLE INC (row ticker INTC) | cusip 37833950 vs holdings file ['037833100'] |
| WARN | cusip_conflict | INTEL CORP (row ticker INTL) | cusip 458140950 vs holdings file ['458140100'] |
| WARN | cusip_conflict | MICROSOFT CORP (row ticker MSFT) | cusip 594918954 vs holdings file ['594918104'] |
| WARN | cusip_conflict | NVIDIA CORPORATION (row ticker NVDA) | cusip 067066G104 vs holdings file ['67066G104'] |
| WARN | cusip_conflict | PG&E CORP (row ticker PCG) | cusip 069331C908 vs holdings file ['69331C108'] |
| WARN | cusip_equals_cik | PAYPAL (row ticker PYPL) | cusip field holds the CIK value 1633917 |
| WARN | cusip_format | AMAZON (row ticker AMZN) | cusip '23135106' has 8 characters, not 9 (leading zeros lost when the CSV was saved?) |
| WARN | cusip_format | AMERICAN INTL GROUP (row ticker AIG) | cusip '26874784' has 8 characters, not 9 (leading zeros lost when the CSV was saved?) |
| WARN | cusip_format | APPLE INC (row ticker AAPL) | cusip '3783310' has 7 characters, not 9 (leading zeros lost when the CSV was saved?) |
| WARN | cusip_format | APPLE INC (row ticker INTC) | cusip '37833950' has 8 characters, not 9 (leading zeros lost when the CSV was saved?) |
| WARN | cusip_format | NVIDIA CORPORATION (row ticker NVDA) | cusip '067066G104' has 10 characters, not 9 |
| WARN | cusip_format | PAYPAL (row ticker PYPL) | cusip '1633917' has 7 characters, not 9 (leading zeros lost when the CSV was saved?) |
| WARN | cusip_format | PG&E CORP (row ticker PCG) | cusip '069331C908' has 10 characters, not 9 |
| WARN | file_unreferenced | 0001652044-16-000012.pdf | PDF has no row in Company_Filings.csv (CIK prefix 1652044, filed 2016) - excluded from the corpus |
| WARN | item1a_short | APPLE INC (row ticker AAPL) | Item 1A is only 163 characters in a 28-page PDF - truncated? |
| WARN | item1a_short | MICROSOFT CORP (row ticker MSFT) | Item 1A is only 3,629 characters in a 2,062-page PDF - truncated? |
| WARN | missing_from_filings_csv | ALPHABET INC | held in holdings file as ['GOOG'] but has no row in Company_Filings.csv |
| WARN | mixed_years | form10k-sample/ | filings from different years: 2016: 0001652044-16-000012.pdf; 2023: 0000320193-23-000106.pdf, 0000950170-23-035122.pdf, 0001004980-23-000029.pdf, 0001018724-23-000004.pdf, 0001045810-23-000017.pdf, 0001096906-23-001489.pdf, 0001633917-23-000033.pdf |
| WARN | name_inconsistent | PAYPAL HLDGS INC | holdings file name differs from Company_Filings.csv ['PAYPAL'] |
| INFO | accession_prefix | APPLE INC (row ticker AAPL) | accession prefix 1096906 differs from CIK 1490054 (fine for a filing agent - worth a look otherwise) |
| INFO | accession_prefix | MICROSOFT CORP (row ticker MSFT) | accession prefix 950170 differs from CIK 789019 (fine for a filing agent - worth a look otherwise) |
| INFO | accession_prefix | PG&E CORP (row ticker PCG) | accession prefix 1004980 differs from CIK 75488 (fine for a filing agent - worth a look otherwise) |
| INFO | share_classes | ALPHABET INC | two CUSIPs (share classes) both labelled ['GOOG'] |
