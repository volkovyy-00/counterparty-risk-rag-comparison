"""taxonomy.yaml as Python objects: category and leaf ids, names, keyword mapping."""
import hashlib
import re

import yaml

import config

_PATH = config.CONFIG_DIR / "taxonomy.yaml"
_RAW = _PATH.read_text()
_DOC = yaml.safe_load(_RAW)

VERSION = _DOC["version"]
SHA256 = hashlib.sha256(_RAW.encode()).hexdigest()
CATEGORIES = _DOC["categories"]
CATEGORY_IDS = [c["id"] for c in CATEGORIES]
CATEGORY_NAMES = {c["id"]: c["name"] for c in CATEGORIES}
LEAVES = {f"{c['id']}.{leaf['id']}": dict(leaf, category=c["id"]) for c in CATEGORIES for leaf in c["leaves"]}
LEAF_IDS = list(LEAVES)
LEAVES_BY_CATEGORY = {c["id"]: [f"{c['id']}.{leaf['id']}" for leaf in c["leaves"]] for c in CATEGORIES}


def leaf_name(leaf_id):
    return leaf_id.split(".", 1)[1].replace("_", " ")


def category_of(leaf_id):
    return LEAVES[leaf_id]["category"] if leaf_id in LEAVES else None


def prompt_listing():
    """The taxonomy as the LLM sees it: categories with their closed leaf lists."""
    lines = []
    for c in CATEGORIES:
        lines.append(f"- {c['id']}: {c['name']} - {c['description']}")
        for leaf in c["leaves"]:
            lines.append(f"    - {c['id']}.{leaf['id']}: {leaf['description']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- keyword mapping
def _pattern(keyword):
    stem = keyword.rstrip("*")
    tail = "" if keyword.endswith("*") else r"\b"
    return re.compile(rf"\b{re.escape(stem)}{tail}", re.I)


CATEGORY_KEYWORDS = {c["id"]: [_pattern(k) for k in c.get("keywords", [])] for c in CATEGORIES}
LEAF_KEYWORDS = {lid: [_pattern(k) for k in leaf.get("keywords", [])] for lid, leaf in LEAVES.items()}


def categories_for(text):
    """Deterministic keyword mapping of free text onto category ids."""
    return [cid for cid, patterns in CATEGORY_KEYWORDS.items() if any(p.search(text) for p in patterns)]


def leaves_for(text):
    """Deterministic keyword mapping of free text onto leaf ids, best match (most keyword hits) first."""
    scored = [(sum(bool(p.search(text)) for p in patterns), lid) for lid, patterns in LEAF_KEYWORDS.items()]
    return [lid for n, lid in sorted(scored, key=lambda x: -x[0]) if n]
