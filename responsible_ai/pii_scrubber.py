"""Conservative regex demonstration, not general-purpose person recognition."""
import re

_PAYEE = re.compile(r"\b(FASTER\s+PAYMENT|TFR\s+TO|STANDING\s+ORDER)\b[^\r\n]*", re.I)
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_POSTCODE = re.compile(r"\b(?:GIR\s*0AA|[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.I)
_PHONE = re.compile(r"(?<!\w)(?:\+44\s*(?:\(0\)\s*)?|0)(?:[\s().-]*\d){9,10}(?!\w)")
_ACCOUNT = re.compile(r"(?<!\w)\d(?:[ -]?\d){7,}(?!\w)")


def scrub_merchant_description(value):
    """Preserve missing scalars and ordinary merchants, including four-digit refs.

    Everything after a transfer/standing-order marker on the same line is
    redacted: regex cannot safely distinguish payee names from references.
    Standalone arbitrary names are not reliably detected. The canary must be
    planted in a payee context, e.g. 'FASTER PAYMENT ZZ TESTNAME'.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        import pandas as pd
        if pd.api.types.is_scalar(value) and pd.isna(value):
            return value
        raise TypeError("merchant_description must be a string or missing scalar")
    value = _PAYEE.sub(lambda m: m.group(1) + " [REDACTED]", value)
    for pattern in (_EMAIL, _POSTCODE, _PHONE, _ACCOUNT):
        value = pattern.sub("[REDACTED]", value)
    return value
