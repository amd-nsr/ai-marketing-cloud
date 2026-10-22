"""Checks generated text against a business's restricted claims and risky phrasing."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

# Language implying guaranteed outcomes, which marketing output must avoid by default.
_GUARANTEE_PATTERNS = [
    r"\bguarantee(d|s)?\b",
    r"\b100\s?% (results|success|satisfaction)\b",
    r"\brisk[- ]free\b",
    r"\bno\.? ?1\b|\bnumber one\b|\b#1\b",
    r"\bbest in the (world|city|country)\b",
]
_GUARANTEE_RE = re.compile("|".join(_GUARANTEE_PATTERNS), re.IGNORECASE)


@dataclass(frozen=True)
class ClaimIssue:
    kind: str  # "restricted_claim" | "guarantee_language"
    phrase: str
    excerpt: str

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "phrase": self.phrase, "excerpt": self.excerpt}


def _excerpt(text: str, start: int, end: int, pad: int = 40) -> str:
    return (
        ("…" if start > pad else "")
        + text[max(0, start - pad) : end + pad].strip()
        + ("…" if end + pad < len(text) else "")
    )


def find_claim_issues(texts: Iterable[str], restricted_claims: Iterable[str]) -> list[ClaimIssue]:
    issues: list[ClaimIssue] = []
    seen: set[tuple[str, str]] = set()
    claims = [c.strip() for c in restricted_claims if c and c.strip()]
    for text in texts:
        if not text:
            continue
        lowered = text.lower()
        for claim in claims:
            idx = lowered.find(claim.lower())
            if idx != -1 and ("restricted_claim", claim) not in seen:
                seen.add(("restricted_claim", claim))
                issues.append(
                    ClaimIssue("restricted_claim", claim, _excerpt(text, idx, idx + len(claim)))
                )
        for match in _GUARANTEE_RE.finditer(text):
            key = ("guarantee_language", match.group(0).lower())
            if key not in seen:
                seen.add(key)
                issues.append(
                    ClaimIssue(
                        "guarantee_language",
                        match.group(0),
                        _excerpt(text, match.start(), match.end()),
                    )
                )
    return issues


def collect_strings(value: object) -> list[str]:
    """All string leaves of a nested JSON-like structure."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in collect_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in collect_strings(v)]
    return []
