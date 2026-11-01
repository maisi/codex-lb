"""Public provenance only exposes an explicit bounded operator label."""

import pytest

from app.core.config.settings import Settings


@pytest.mark.parametrize("label", ["oci-a", "home-b", "a", "A_b-9", "n" * 64])
def test_explicit_processing_labels(label, monkeypatch):
    monkeypatch.setenv("CODEX_LB_HTTP_RESPONSES_SESSION_BRIDGE_INSTANCE_ID", label)
    assert Settings(_env_file=None).processing_node == label


@pytest.mark.parametrize(
    "label",
    [
        "",
        " ",
        "10.0.0.1",
        "::1",
        "host.internal",
        "/srv/host",
        "https://user:secret@host",
        "user:secret",
        "a b",
        "é-node",
        "n" * 65,
        "sk-fixture-secret",
        "ghp_fixturesecret",
        "github_pat_fixturesecret",
    ],
)
def test_unsafe_processing_labels_are_unknown(label):
    assert Settings(_env_file=None, http_responses_session_bridge_instance_id=label).processing_node is None


def test_default_hostname_is_not_a_public_processing_label(monkeypatch):
    monkeypatch.delenv("CODEX_LB_HTTP_RESPONSES_SESSION_BRIDGE_INSTANCE_ID", raising=False)
    monkeypatch.setattr("app.core.config.settings.socket.gethostname", lambda: "private-host-fixture")
    settings = Settings(_env_file=None)
    assert settings.http_responses_session_bridge_instance_id == "private-host-fixture"
    assert settings.processing_node is None
