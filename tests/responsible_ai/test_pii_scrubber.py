import pandas as pd
import pytest

from responsible_ai.pii_scrubber import scrub_merchant_description as scrub


@pytest.mark.parametrize("text,expected", [
    ("FASTER PAYMENT JOHN SMITH", "FASTER PAYMENT [REDACTED]"),
    ("TFR TO A. KUMAR", "TFR TO [REDACTED]"),
    ("standing order Jane Smith", "standing order [REDACTED]"),
    ("CONTACT john.smith@example.com", "CONTACT [REDACTED]"),
    ("PHONE +44 7700 900123", "PHONE [REDACTED]"),
    ("PHONE 020 7946 0958", "PHONE [REDACTED]"),
    ("POST SW1A 1AA", "POST [REDACTED]"),
    ("POST sw1a1aa", "POST [REDACTED]"),
    ("ACCOUNT 123456789012", "ACCOUNT [REDACTED]"),
    ("ACCOUNT 1234 5678 9012", "ACCOUNT [REDACTED]"),
    ("TEXACO FUEL 4265", "TEXACO FUEL 4265"),
    ("OCTOPUS ENERGY GAS 4043", "OCTOPUS ENERGY GAS 4043"),
    ("FASTER PAYMENT ZZ TESTNAME", "FASTER PAYMENT [REDACTED]"),
])
def test_scrub(text, expected):
    assert scrub(text) == expected
    assert scrub(scrub(text)) == expected


def test_missing_and_invalid():
    assert scrub(None) is None
    assert scrub(pd.NA) is pd.NA
    assert pd.isna(scrub(float("nan")))
    with pytest.raises(TypeError):
        scrub(12345)
