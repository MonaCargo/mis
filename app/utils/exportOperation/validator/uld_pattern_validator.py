# # app/validators/uld_pattern.py
# """
# ULD pattern validator.

# Single source of truth for all allowed ULD number formats.
# Used by both Pydantic schemas (request validation) and the service layer
# (defence-in-depth).

# Patterns mirror the reference table:
#     - AI column  → AKE/PMC/PKC/PAG/PAJ/PLA + digits + "AI"
#     - BT range   → BT + 2..4 digits (no suffix)
#     - R9 column  → 13 prefixes + 5 digits + "R9"
#     - R7 column  → same 13 prefixes + 5 digits + "R7"
# """

# import re
# from dataclasses import dataclass
# from typing import List, Optional


# @dataclass(frozen=True)
# class UldPattern:
#     """One allowed ULD shape."""
#     uld_type: str          # AKE, PMC, BT, etc.
#     regex: re.Pattern      # compiled, full-string anchored
#     example: str           # for error messages


# # Prefixes that appear in both R9 and R7 columns
# _R_PREFIXES = (
#     "AKE", "AMF", "ALF", "AAP", "AMP", "FLA",
#     "PAG", "PMC", "PAJ", "PLA", "PKC", "RAP", "PLB",
# )


# def _build_patterns() -> List[UldPattern]:
#     patterns: List[UldPattern] = [
#         # ---- AI column (suffix "AI") ----
#         UldPattern("AKE", re.compile(r"^AKE\d{4,5}AI$"),     "AKE12345AI"),
#         UldPattern("PMC", re.compile(r"^PMC\d{4,5}AI$"),   "PMC12345AI"),
#         UldPattern("PKC", re.compile(r"^PKC\d{4,5}AI$"),   "PKC12345AI"),
#         UldPattern("PAG", re.compile(r"^PAG\d{4,5}AI$"),   "PAG12345AI"),
#         UldPattern("PAJ", re.compile(r"^PAJ\d{4,5}AI$"),   "PAJ12345AI"),
#         UldPattern("PLA", re.compile(r"^PLA\d{5}AI$"),     "PLA12345AI"),

#         # ---- BT range (no suffix) ----
#         UldPattern("BT",  re.compile(r"^BT\d{2,4}$"),      "BT1234"),
#     ]

#     # R9 patterns
#     for p in _R_PREFIXES:
#         patterns.append(
#             UldPattern(p, re.compile(rf"^{p}\d{{5}}R9$"), f"{p}12345R9")
#         )

#     # R7 patterns
#     for p in _R_PREFIXES:
#         patterns.append(
#             UldPattern(p, re.compile(rf"^{p}\d{{5}}R7$"), f"{p}12345R7")
#         )

#     return patterns


# ULD_PATTERNS: List[UldPattern] = _build_patterns()


# @dataclass(frozen=True)
# class UldValidationResult:
#     is_valid: bool
#     uld_type: Optional[str] = None
#     matched_example: Optional[str] = None
#     reason: Optional[str] = None
#     suggestions: Optional[List[str]] = None


# def validate_uld_no(raw: str) -> UldValidationResult:
#     """
#     Validate a ULD number against every known pattern.

#     Returns a structured result so the API can surface a helpful error
#     when validation fails.
#     """
#     if not raw or not isinstance(raw, str):
#         return UldValidationResult(
#             is_valid=False,
#             reason="ULD number is required.",
#             suggestions=[],
#         )

#     value = raw.strip().upper()

#     if not value:
#         return UldValidationResult(
#             is_valid=False,
#             reason="ULD number cannot be empty.",
#             suggestions=[],
#         )

#     # 1. Exact pattern match
#     for p in ULD_PATTERNS:
#         if p.regex.match(value):
#             return UldValidationResult(
#                 is_valid=True,
#                 uld_type=p.uld_type,
#                 matched_example=p.example,
#             )

#     # 2. Cheap structural rejection
#     if not re.fullmatch(r"[A-Z0-9]+", value):
#         return UldValidationResult(
#             is_valid=False,
#             reason="Only letters (A-Z) and digits (0-9) are allowed.",
#             suggestions=[],
#         )

#     # 3. Helpful "did you mean…" guidance based on prefix
#     prefix_matches = []
#     for p in ULD_PATTERNS:
#         # Extract the literal prefix from each regex (the leading [A-Z]+ after ^)
#         m = re.match(r"\^([A-Z]+)", p.regex.pattern)
#         if m and value.startswith(m.group(1)):
#             prefix_matches.append((len(m.group(1)), p))

#     if prefix_matches:
#         # Longer prefix wins (AKE beats A, PMC beats PM, etc.)
#         prefix_matches.sort(key=lambda x: -x[0])
#         best = prefix_matches[0][1]
#         return UldValidationResult(
#             is_valid=False,
#             reason=f"'{value}' does not match the expected format for {best.uld_type}.",
#             suggestions=[p.example for _, p in prefix_matches[:3]],
#         )

#     # 4. Completely unknown prefix
#     allowed = sorted({
#         re.match(r"\^([A-Z]+)", p.regex.pattern).group(1)
#         for p in ULD_PATTERNS
#         if re.match(r"\^([A-Z]+)", p.regex.pattern)
#     })

#     return UldValidationResult(
#         is_valid=False,
#         reason=(
#             "Prefix not recognised. ULD must start with one of: "
#             + ", ".join(allowed[:10]) + "…"
#         ),
#         suggestions=["AKE1234AI", "PMC12345AI", "BT1234", "AMF12345R9", "PAG12345R7"],
#     )









# app/validators/uld_pattern.py
"""
ULD pattern validator.

Rules:
  - PREFIX + 3–6 digits + suffix
      suffix:
        - starts with R + digit  → must be exactly R9 or R7
        - starts with R + letter → 2–3 letters total (e.g. RK, RKN)
        - anything else          → 2–3 pure letters (e.g. AI, XY, ABC)
  - BT  → BT + 2–4 digits (no suffix)
  - PD  → PD + 2–4 digits (no suffix)
"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class UldValidationResult:
    is_valid: bool
    uld_type: Optional[str] = None
    matched_example: Optional[str] = None
    reason: Optional[str] = None
    suggestions: Optional[List[str]] = None


ULD_PREFIXES = [
    "AKE", "AMF", "ALF", "AAP", "AMP", "FLA", "RKN", "RAP", "PLB",
    "PMC", "PKC", "PAG", "PAJ", "PLA","AAF",
]

# Sort longest first so AKE is matched before AK, etc.
ULD_PREFIXES_SORTED = sorted(ULD_PREFIXES, key=len, reverse=True)


def _validate_suffix(suffix: str) -> bool:
    """
    Suffix rules:
      - starts with R:
          next char is digit → must be exactly R9 or R7 (nothing more)
          next char is letter → total 2–3 letters (all alpha)
      - otherwise → 2–3 pure letters (A–Z)
    """
    if not suffix:
        return False
    
    # Exact special suffixes — checked first before any letter-based rules
    if suffix in ("R9", "R7", "W5"):
        return True

    if suffix[0] == "R":
        if len(suffix) < 2:
            return False  # just "R" alone

        next_char = suffix[1]

        if next_char.isdigit():
            # R + digit → only R9 or R7 exactly
            return suffix in ("R9", "R7","W5")
        else:
            # R + letter → treat as normal 2–3 letter suffix
            return 2 <= len(suffix) <= 3 and suffix.isalpha()

    # No R start → 2–3 pure letters
    return 2 <= len(suffix) <= 3 and suffix.isalpha()


def validate_uld_no(raw: str) -> UldValidationResult:
    """
    Validate a ULD number against the allowed patterns.
    Returns a structured result for helpful error surfacing.
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

    # ── Structural check ────────────────────────────────────────────────────
    if not re.fullmatch(r"[A-Z0-9]+", value):
        return UldValidationResult(
            is_valid=False,
            reason="Only letters (A–Z) and digits (0–9) are allowed — no spaces or symbols.",
            suggestions=[],
        )

    # ── BT rule ─────────────────────────────────────────────────────────────
    if value.startswith("BT"):
        digits = value[2:]
        if re.fullmatch(r"\d{2,5}", digits):
            return UldValidationResult(
                is_valid=True,
                uld_type="BT",
                matched_example="BT12345",
            )
        return UldValidationResult(
            is_valid=False,
            reason=f"BT must be followed by 2–5 digits only. e.g. BT12, BT12345",
            suggestions=["BT12", "BT123", "BT1234", "BT12345"],
        )

    # ── PD rule (same as BT) ─────────────────────────────────────────────────
    if value.startswith("PD"):
        digits = value[2:]
        if re.fullmatch(r"\d{2,5}", digits):
            return UldValidationResult(
                is_valid=True,
                uld_type="PD",
                matched_example="PD12345",
            )
        return UldValidationResult(
            is_valid=False,
            reason=f"PD must be followed by 2–5 digits only. e.g. PD12, PD12345",
            suggestions=["PD12", "PD123", "PD1234", "PD12345"],
        )

    # ── Prefix match ─────────────────────────────────────────────────────────
    matched_prefix = next(
        (p for p in ULD_PREFIXES_SORTED if value.startswith(p)),
        None,
    )

    if not matched_prefix:
        return UldValidationResult(
            is_valid=False,
            reason=(
                f"Prefix not recognised. Must start with one of: "
                f"{', '.join(ULD_PREFIXES)}, BT, PD"
            ),
            suggestions=["AKE123AI", "PMC12345R9", "BT1234", "PD1234", "AMF123RKN"],
        )

    rest = value[len(matched_prefix):]  # everything after prefix

    # ── Split into digits + suffix ───────────────────────────────────────────
    m = re.match(r"^(\d+)([A-Z][A-Z0-9]*)$", rest)

    if not m:
        return UldValidationResult(
            is_valid=False,
            reason=(
                f"After '{matched_prefix}', expected 3–6 digits then 2–3 letters "
                f"(e.g. {matched_prefix}123AI or {matched_prefix}12345R9)."
            ),
            suggestions=[
                f"{matched_prefix}123AI",
                f"{matched_prefix}12345R9",
                f"{matched_prefix}1234RK",
            ],
        )

    digits = m.group(1)
    suffix = m.group(2)

    # ── Digit count ──────────────────────────────────────────────────────────
    if not (3 <= len(digits) <= 6):
        return UldValidationResult(
            is_valid=False,
            reason=(
                f"'{matched_prefix}' must be followed by 3–6 digits, "
                f"got {len(digits)}."
            ),
            suggestions=[
                f"{matched_prefix}123AI",
                f"{matched_prefix}12345R9",
                f"{matched_prefix}123456AB",
            ],
        )

    # ── Suffix check ─────────────────────────────────────────────────────────
    if not _validate_suffix(suffix):
        return UldValidationResult(
            is_valid=False,
            reason=(
                f"Invalid suffix '{suffix}'. Use 2–3 letters (e.g. AI, RKN), "
                f"or exactly R9 / R7 / W5."
            ),
            suggestions=[
                f"{matched_prefix}{digits}AI",
                f"{matched_prefix}{digits}R9",
                f"{matched_prefix}{digits}R7",
                f"{matched_prefix}{digits}W5",
            ],
        )

    # ── All good ─────────────────────────────────────────────────────────────
    return UldValidationResult(
        is_valid=True,
        uld_type=matched_prefix,
        matched_example=f"{matched_prefix}{digits}{suffix}",
    )