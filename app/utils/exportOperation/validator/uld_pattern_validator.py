# app/validators/uld_pattern.py
"""
ULD pattern validator.

Single source of truth for all allowed ULD number formats.
Used by both Pydantic schemas (request validation) and the service layer
(defence-in-depth).

Patterns mirror the reference table:
    - AI column  → AKE/PMC/PKC/PAG/PAJ/PLA + digits + "AI"
    - BT range   → BT + 2..4 digits (no suffix)
    - R9 column  → 13 prefixes + 5 digits + "R9"
    - R7 column  → same 13 prefixes + 5 digits + "R7"
"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class UldPattern:
    """One allowed ULD shape."""
    uld_type: str          # AKE, PMC, BT, etc.
    regex: re.Pattern      # compiled, full-string anchored
    example: str           # for error messages


# Prefixes that appear in both R9 and R7 columns
_R_PREFIXES = (
    "AKE", "AMF", "ALF", "AAP", "AMP", "FLA",
    "PAG", "PMC", "PAJ", "PLA", "PKC", "RAP", "PLB",
)


def _build_patterns() -> List[UldPattern]:
    patterns: List[UldPattern] = [
        # ---- AI column (suffix "AI") ----
        UldPattern("AKE", re.compile(r"^AKE\d{4}AI$"),     "AKE1234AI"),
        UldPattern("PMC", re.compile(r"^PMC\d{4,5}AI$"),   "PMC12345AI"),
        UldPattern("PKC", re.compile(r"^PKC\d{4,5}AI$"),   "PKC12345AI"),
        UldPattern("PAG", re.compile(r"^PAG\d{4,5}AI$"),   "PAG12345AI"),
        UldPattern("PAJ", re.compile(r"^PAJ\d{4,5}AI$"),   "PAJ12345AI"),
        UldPattern("PLA", re.compile(r"^PLA\d{5}AI$"),     "PLA12345AI"),

        # ---- BT range (no suffix) ----
        UldPattern("BT",  re.compile(r"^BT\d{2,4}$"),      "BT1234"),
    ]

    # R9 patterns
    for p in _R_PREFIXES:
        patterns.append(
            UldPattern(p, re.compile(rf"^{p}\d{{5}}R9$"), f"{p}12345R9")
        )

    # R7 patterns
    for p in _R_PREFIXES:
        patterns.append(
            UldPattern(p, re.compile(rf"^{p}\d{{5}}R7$"), f"{p}12345R7")
        )

    return patterns


ULD_PATTERNS: List[UldPattern] = _build_patterns()


@dataclass(frozen=True)
class UldValidationResult:
    is_valid: bool
    uld_type: Optional[str] = None
    matched_example: Optional[str] = None
    reason: Optional[str] = None
    suggestions: Optional[List[str]] = None


def validate_uld_no(raw: str) -> UldValidationResult:
    """
    Validate a ULD number against every known pattern.

    Returns a structured result so the API can surface a helpful error
    when validation fails.
    """
    if not raw or not isinstance(raw, str):
        return UldValidationResult(
            is_valid=False,
            reason="ULD number is required.",
            suggestions=[],
        )

    value = raw.strip().upper()

    if not value:
        return UldValidationResult(
            is_valid=False,
            reason="ULD number cannot be empty.",
            suggestions=[],
        )

    # 1. Exact pattern match
    for p in ULD_PATTERNS:
        if p.regex.match(value):
            return UldValidationResult(
                is_valid=True,
                uld_type=p.uld_type,
                matched_example=p.example,
            )

    # 2. Cheap structural rejection
    if not re.fullmatch(r"[A-Z0-9]+", value):
        return UldValidationResult(
            is_valid=False,
            reason="Only letters (A-Z) and digits (0-9) are allowed.",
            suggestions=[],
        )

    # 3. Helpful "did you mean…" guidance based on prefix
    prefix_matches = []
    for p in ULD_PATTERNS:
        # Extract the literal prefix from each regex (the leading [A-Z]+ after ^)
        m = re.match(r"\^([A-Z]+)", p.regex.pattern)
        if m and value.startswith(m.group(1)):
            prefix_matches.append((len(m.group(1)), p))

    if prefix_matches:
        # Longer prefix wins (AKE beats A, PMC beats PM, etc.)
        prefix_matches.sort(key=lambda x: -x[0])
        best = prefix_matches[0][1]
        return UldValidationResult(
            is_valid=False,
            reason=f"'{value}' does not match the expected format for {best.uld_type}.",
            suggestions=[p.example for _, p in prefix_matches[:3]],
        )

    # 4. Completely unknown prefix
    allowed = sorted({
        re.match(r"\^([A-Z]+)", p.regex.pattern).group(1)
        for p in ULD_PATTERNS
        if re.match(r"\^([A-Z]+)", p.regex.pattern)
    })

    return UldValidationResult(
        is_valid=False,
        reason=(
            "Prefix not recognised. ULD must start with one of: "
            + ", ".join(allowed[:10]) + "…"
        ),
        suggestions=["AKE1234AI", "PMC12345AI", "BT1234", "AMF12345R9", "PAG12345R7"],
    )