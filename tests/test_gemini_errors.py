"""Tests for classifying Gemini API failures (the 'out of credits' signal)."""

from google.genai import errors

from birdscreen.gemini import classify_api_error, is_gemini_error


class _FakeApiError(Exception):
    """Stand-in for google.genai errors that carry an HTTP ``code``."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


# The real depletion error Google returns (429 RESOURCE_EXHAUSTED, billing message).
_DEPLETED = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': "
    "'Your prepayment credits are depleted. Please go to AI Studio to manage billing.', "
    "'status': 'RESOURCE_EXHAUSTED'}}"
)


def test_depleted_credits_is_out_of_credits() -> None:
    kind, message = classify_api_error(_FakeApiError(429, _DEPLETED))
    assert kind == "out_of_credits"
    assert "credit" in message.lower()


def test_plain_rate_limit_is_transient_not_credits() -> None:
    # A 429 without any billing wording is a self-healing rate limit, not depletion.
    kind, _ = classify_api_error(
        _FakeApiError(429, "429 RESOURCE_EXHAUSTED. Quota exceeded for requests per minute.")
    )
    assert kind == "rate_limited"


def test_missing_key_runtimeerror_is_no_key() -> None:
    kind, _ = classify_api_error(RuntimeError("No Gemini API key found. Set GEMINI_API_KEY."))
    assert kind == "no_key"


def test_bad_key_is_auth() -> None:
    kind, _ = classify_api_error(_FakeApiError(403, "API key not valid. Please pass a valid key."))
    assert kind == "auth"


def test_unknown_failure_is_generic_error() -> None:
    kind, _ = classify_api_error(Exception("connection reset by peer"))
    assert kind == "error"


def test_real_client_error_is_a_gemini_error() -> None:
    # A genuine google-genai 429 must be attributed to Gemini (so it's recorded).
    exc = errors.ClientError(429, {"error": {"code": 429, "message": _DEPLETED, "status": "x"}})
    assert is_gemini_error(exc) is True
    assert classify_api_error(exc)[0] == "out_of_credits"


def test_missing_key_is_a_gemini_error() -> None:
    assert is_gemini_error(RuntimeError("No Gemini API key found. Set GEMINI_API_KEY.")) is True


def test_downstream_failures_are_not_gemini_errors() -> None:
    # These share the generation code path but must NOT be branded as Gemini problems.
    assert is_gemini_error(RuntimeError("No location configured — set it in Settings.")) is False
    assert is_gemini_error(OSError("No space left on device")) is False
    assert is_gemini_error(Exception("Samsung TV unreachable")) is False
