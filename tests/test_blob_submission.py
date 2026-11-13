
"""Verify exact signed-blob submission without network access."""

from unittest.mock import MagicMock

from xrpl.models.requests import SubmitOnly

from rules_server.execution import submit_signed_blob


def test_submits_exact_signed_blob():
    client = MagicMock()
    blob = "DEADBEEF"

    submit_signed_blob(client, blob)

    client.request.assert_called_once()

    request = client.request.call_args.args[0]

    assert isinstance(request, SubmitOnly)
    assert request.tx_blob == blob
    assert request.fail_hard is True
