"""Groq client factory — SSL settings and connection retry."""

import os
import ssl

import certifi
import httpx
from groq import APIConnectionError, Groq


def ssl_verify_setting() -> bool | str:
    """Resolve SSL verification — false bypasses corporate Zscaler cert issues."""
    ssl_setting = os.getenv("GROQ_SSL_VERIFY", "false").lower()
    if ssl_setting in ("false", "0", "no"):
        return False
    if cert_path := os.getenv("SSL_CERT_FILE"):
        return ssl.create_default_context(cafile=cert_path)
    return certifi.where()


def create_groq_client(*, verify: bool | str | ssl.SSLContext | None = None) -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set. Get a free key at https://console.groq.com")

    if verify is None:
        verify = ssl_verify_setting()

    http_client = httpx.Client(verify=verify, timeout=60.0)
    return Groq(api_key=api_key, http_client=http_client)


class GroqChatClient:
    """Thin wrapper: auto-retry once with SSL verification disabled on cert errors."""

    def __init__(self) -> None:
        self._ssl_verify = ssl_verify_setting()
        self.client = create_groq_client(verify=self._ssl_verify)

    def _recreate_without_ssl(self) -> None:
        self._ssl_verify = False
        self.client = create_groq_client(verify=False)

    def create(self, **kwargs):
        try:
            return self.client.chat.completions.create(**kwargs)
        except APIConnectionError:
            if self._ssl_verify is not False:
                self._recreate_without_ssl()
                return self.client.chat.completions.create(**kwargs)
            raise
