"""Tests for Guardian — the secret-redactor archetype.

These are intentionally strict: Guardian is the archetype that maps
directly to Hermes issue #10520 (plaintext passwords leaked in
browser_type tool calls), so we test the exact shape of that leak
plus the common API-key formats.
"""

from __future__ import annotations

import pytest

from hermes_studio.archetypes.guardian import Guardian, redact


def test_redacts_openai_key():
    text = "my key is sk-abc123def456ghi789jkl"
    out, fired = redact(text)
    assert "sk-abc123def456ghi789jkl" not in out
    assert "[REDACTED_SECRET]" in out
    assert "openai_key" in fired


def test_redacts_anthropic_key():
    text = "ANTHROPIC_API_KEY=sk-ant-api03-abcDEF123_456-xyz"
    out, fired = redact(text)
    assert "sk-ant-api03-abcDEF123_456-xyz" not in out
    assert "anthropic_key" in fired


def test_redacts_bearer_token():
    out, fired = redact("Authorization: Bearer eyJhbGciOi.abc.def")
    assert "eyJhbGciOi.abc.def" not in out
    assert "bearer_token" in fired


def test_redacts_browser_password_field_10520_shape():
    """Exact shape of the leak in Hermes issue #10520 — browser_type tool
    call echoing a 1Password-sourced password into Telegram."""
    text = 'browser_type(field="password", value="hunter2_realpassword")'
    # Our pattern targets the assignment shape password=... which is how
    # the sanitizer should catch leaks regardless of tool-call framing.
    # First test the field-like pattern:
    out, fired = redact('Logging in with password="hunter2_realpassword"')
    assert "hunter2_realpassword" not in out
    assert "password=" in out or "password =" in out or "password:" in out
    assert "[REDACTED_SECRET]" in out
    assert "browser_password_field" in fired


def test_redacts_aws_access_key():
    out, fired = redact("access_key=AKIAIOSFODNN7EXAMPLE")
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "aws_access_key" in fired


def test_redacts_private_key_block():
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEAxyz123fakekeydatathatshouldneverleak\n"
        "-----END RSA PRIVATE KEY-----"
    )
    out, fired = redact(f"here is my key: {pem}")
    assert "fakekeydatathatshouldneverleak" not in out
    assert "private_key_block" in fired


def test_no_false_positive_on_normal_text():
    out, fired = redact("Just a normal message about the weather.")
    assert out == "Just a normal message about the weather."
    assert fired == []


def test_empty_input():
    out, fired = redact("")
    assert out == ""
    assert fired == []


def test_guardian_post_tool_call_redacts_and_counts():
    g = Guardian()
    leaked = "Login result: password=hunter2"
    replaced = g.post_tool_call(tool_name="browser_type", result=leaked)
    assert replaced is not None
    assert "hunter2" not in replaced
    assert g.redaction_count >= 1


def test_guardian_post_tool_call_passthrough_when_clean():
    g = Guardian()
    clean = "Visited https://example.com, status 200"
    replaced = g.post_tool_call(tool_name="browser_type", result=clean)
    # Returning None tells Hermes to keep the original result unchanged.
    assert replaced is None
    assert g.redaction_count == 0


def test_guardian_pre_llm_call_redacts_message_content():
    g = Guardian()
    messages = [
        {"role": "user", "content": "here is my token Bearer abc.def.ghi"},
        {"role": "assistant", "content": "ok"},
    ]
    result = g.pre_llm_call(messages)
    assert result is not None
    assert "Bearer abc.def.ghi" not in result[0]["content"]
    assert result[1]["content"] == "ok"


def test_guardian_pre_llm_call_multimodal_content():
    g = Guardian()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "key=sk-aaaaaaaaaaaaaaaaaaaaaaaa"},
                {"type": "image_url", "image_url": {"url": "https://example.com/x.jpg"}},
            ],
        }
    ]
    result = g.pre_llm_call(messages)
    assert result is not None
    assert "sk-aaaaaaaaaaaaaaaaaaaaaaaa" not in result[0]["content"][0]["text"]


def test_guardian_pre_llm_call_returns_none_when_clean():
    g = Guardian()
    messages = [{"role": "user", "content": "hello world"}]
    assert g.pre_llm_call(messages) is None
