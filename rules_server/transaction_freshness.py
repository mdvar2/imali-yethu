
"""Verify XRPL payment sequence and ledger expiry."""

from xrpl.models.requests import AccountInfo, LedgerCurrent


def verify_transaction_freshness(client, transaction, treasury):
    """Check that a prepared payment is current and not expired."""

    if transaction.get("Account") != treasury:
        return False, "Unexpected Treasury account"

    sequence = transaction.get("Sequence")
    last_ledger = transaction.get("LastLedgerSequence")

    if (
        type(sequence) is not int
        or type(last_ledger) is not int
        or sequence < 0
        or last_ledger <= 0
    ):
        return False, "Invalid transaction sequence or expiry"

    account_response = client.request(
        AccountInfo(
            account=treasury,
            ledger_index="validated",
        )
    )

    ledger_response = client.request(LedgerCurrent())

    if (
        not account_response.is_successful()
        or not ledger_response.is_successful()
    ):
        return False, "Unable to verify ledger freshness"

    expected_sequence = account_response.result["account_data"]["Sequence"]
    current_ledger = ledger_response.result["ledger_current_index"]

    if sequence != expected_sequence:
        return False, "Treasury sequence mismatch"

    if last_ledger <= current_ledger:
        return False, "Transaction has expired"

    if last_ledger > current_ledger + 100:
        return False, "Transaction expiry is too far in the future"

    return True, "Transaction is fresh"
