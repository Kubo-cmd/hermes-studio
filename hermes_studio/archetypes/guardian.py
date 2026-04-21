"""
Guardian — the secret redactor.

Addresses Hermes issue #10520 (plaintext passwords leaked to Telegram).
Hooks into pre_llm_call (to redact outgoing context, though in practice
secrets shouldn't flow out of the user side) and post_tool_call (to redact
tool outputs before they stream back to the user-facing gateway).

This is additive to Hermes's own privacy.redact_pii — Guardian focuses
specifically on credentials that show up in browser automation flows,
shell output, and tool results, which is where #10520 originated.

Patterns are based on the actual leak in #10520 (browser_type call that
echoed a 1Password-sourced password) plus common API key formats. The
list is conservative — false positives are preferred over misses.
"""

from __future__ import annotations

import re
from typing import Any

# Patterns are applied in order. Named groups let us log *which* category
# fired without exposing the value.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}")),
    ("bearer_token", re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-_\.=]+")),
    ("generic_api_key", re.compile(r"(?i)\bapi[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9\-_\.]{16,}")),
    # #10520 shape: browser_type tool call with password field
    ("browser_password_field", re.compile(
        r"(?i)(?P<prefix>password\s*[:=]\s*['\"]?)(?P<value>\S+?)(?P<suffix>['\"]?(?=[\s,}\)]|$))"
    )),
    # AWS-style
    ("aws_access_key", re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b")),
    # Private keys
    ("private_key_block", re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"
    )),
]

_REDACTED = "[REDACTED_SECRET]"


def redact(text: str) -> tuple[str, list[str]]:
    """Redact secrets from `text`.

    Returns the redacted string and a list of category names that fired.
    Never includes the original value in the returned list.
    """
    if not text:
        return text, []
    fired: list[str] = []
    out = text
    for name, pat in _PATTERNS:
        if pat.search(out):
            fired.append(name)
            # For the browser_password_field pattern, keep the key name visible
            # but redact just the value so the user still knows what was sanitized.
            if name == "browser_password_field":
                out = pat.sub(lambda m: f"{m.group('prefix')}{_REDACTED}{m.group('suffix')}", out)
            else:
                out = pat.sub(_REDACTED, out)
    return out, fired


class Guardian:
    """Secret-redacting hook component."""

    def __init__(self) -> None:
        self._redaction_count: int = 0

    def pre_llm_call(self, messages: list[dict], **kwargs: Any) -> list[dict] | None:
        """Redact outbound messages before they reach the LLM provider.

        Hermes's pre_llm_call hook convention: if the hook returns a value,
        it replaces `messages`. If it returns None, messages are unchanged.
        """
        changed = False
        for m in messages:
            content = m.get("content")
            if isinstance(content, str):
                new, fired = redact(content)
                if fired:
                    m["content"] = new
                    self._redaction_count += len(fired)
                    changed = True
            elif isinstance(content, list):
                # Multi-modal content blocks
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        new, fired = redact(block.get("text", ""))
                        if fired:
                            block["text"] = new
                            self._redaction_count += len(fired)
                            changed = True
        return messages if changed else None

    def post_tool_call(self, tool_name: str, result: str, **kwargs: Any) -> str | None:
        """Redact tool results before they go back into the conversation.

        Returning a string replaces the result; returning None leaves it.
        """
        if not isinstance(result, str):
            return None
        new, fired = redact(result)
        if fired:
            self._redaction_count += len(fired)
            return new
        return None

    @property
    def redaction_count(self) -> int:
        return self._redaction_count
