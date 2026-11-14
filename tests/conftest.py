import pytest

from rules_server import authorization, policy


@pytest.fixture(autouse=True)
def isolated_rules_state(tmp_path, monkeypatch):
    """Keep tests away from the real policy file and authorization database."""
    monkeypatch.setattr(policy, "DATA_DIR", tmp_path)
    monkeypatch.setattr(policy, "POLICY_PATH", tmp_path / "policy.json")
    monkeypatch.setattr(policy, "AUDIT_PATH", tmp_path / "policy_audit.jsonl")
    monkeypatch.setattr(authorization, "DB_PATH", tmp_path / "authorizations.db")
    # The local .env may set SIGNING_MODE (e.g. multisig after setup_multisig.py).
    # Tests choose their own signing mode, so never inherit it.
    monkeypatch.delenv("SIGNING_MODE", raising=False)
