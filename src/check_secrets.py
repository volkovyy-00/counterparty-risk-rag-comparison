"""Scan for secrets before every commit: tracked files, cache/ and results/.

    python src/check_secrets.py        # exit 1 and list findings if anything looks like a key

Uses gitleaks when it is installed (make check-secrets), and always runs this
regex scan as well. The local Neo4j default password is allowed by name only.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "anthropic key": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "openai key": r"sk-(?:proj-)?[A-Za-z0-9_\-]{32,}",
    "aws access key": r"\bAKIA[0-9A-Z]{16}\b",
    "github token": r"\bgh[pousr]_[A-Za-z0-9]{30,}\b",
    "google api key": r"\bAIza[0-9A-Za-z_\-]{35}\b",
    "slack token": r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "key assignment": r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[=:]\s*['\"]?(?!demo-password\b)(?!your)[A-Za-z0-9_\-]{24,}",
}
SKIP_SUFFIX = {".png", ".jpg", ".pdf", ".mp4", ".pyc"}


def files():
    tracked = subprocess.run(["git", "ls-files", "-z", "."], cwd=ROOT, capture_output=True, text=True).stdout
    out = {ROOT / p for p in tracked.split("\0") if p}
    for extra in ("cache", "results", "demo"):
        out |= {p for p in (ROOT / extra).rglob("*") if p.is_file()}
    return sorted(p for p in out if p.exists() and p.suffix not in SKIP_SUFFIX and p.name != ".env")


def scan():
    findings = []
    compiled = {name: re.compile(p) for name, p in PATTERNS.items()}
    for path in files():
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for name, pattern in compiled.items():
            for m in pattern.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                findings.append(f"{path.relative_to(ROOT)}:{line}: {name}: {m.group()[:12]}...")
    return findings


def main():
    findings = scan()
    gitignore = (ROOT / ".gitignore").read_text() if (ROOT / ".gitignore").exists() else ""
    if ".env" not in gitignore.split():
        findings.append(".gitignore: .env is not ignored")
    if findings:
        print("Possible secrets found:\n" + "\n".join(findings))
        sys.exit(1)
    print(f"check-secrets: {len(files())} files scanned, nothing found")


if __name__ == "__main__":
    main()
