
"""Verify XRPL signed-blob submission without network access."""

from unittest.mock import MagicMock

import pytest
from xrpl.models.requests import SubmitOnly

from rules_server.execution import (
    inspect_submission_response,
    submit_signed_blob,
)


def test_submits_exact_signed_blob():
    client = MagicMock()
    blob = "DEADBEEF"

    submit_signed_blob(client, blob)

    client.request.assert_called_once()

    request = client.request.call_args.args[0]

    assert isinstance(request, SubmitOnly)
    assert request.tx_blob == blob
    assert request.fail_hard is True


@pytest.mark.parametrize(
    ("engine_result", "expected_status"),
    [
        ("tesSUCCESS", "provisional"),
        ("terQUEUED", "provisional"),
        ("terPRE_SEQ", "provisional"),
        ("tecPATH_DRY", "rejected"),
        ("temBAD_SIGNATURE", "rejected"),
        ("tefPAST_SEQ", "rejected"),
        ("telINSUF_FEE_P", "rejected"),
    ],
)
def test_classifies_submission_response(
    engine_result,
    expected_status,
):
    response = MagicMock()
    response.result = {"engine_result": engine_result}

    status, reason = inspect_submission_response(response)

    assert status == expected_status
    assert reason == engine_result


def test_missing_submission_response_is_unknown():
    response = MagicMock()
    response.result = {}

    status, reason = inspect_submission_response(response)

    assert status == "unknown"
    assert reason == "Missing XRPL engine result"


def test_invalid_submission_response_is_unknown():
    response = MagicMock()
    response.result = None

    status, reason = inspect_submission_response(response)

    assert status == "unknown"
    assert reason == "Missing XRPL submission response"


def test_unrecognized_engine_result_is_unknown():
    response = MagicMock()
    response.result = {"engine_result": "unexpected"}

    status, reason = inspect_submission_response(response)

    assert status == "unknown"
    assert reason == "unexpected"
