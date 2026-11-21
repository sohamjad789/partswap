"""NVIDIA Nemotron Parse client. It accepts a single rendered page, never a PDF."""

import re

import httpx

from app.config import get_settings

COORDINATES = re.compile(r"<x_[0-9.]+>|<y_[0-9.]+>|<class_[^>]+>")


def parse_page(png: bytes) -> str | None:
    settings = get_settings()
    if not png or not settings.has_api_key:
        return None
    try:
        response = httpx.post(
            settings.parse_url,
            headers={"Authorization": f"Bearer {settings.nvidia_api_key}"},
            files={"document": ("page.png", png, "image/png")},
            data={"options": '{"decoding":{"max_output_tokens":4096}}'},
            timeout=30,
        )
        response.raise_for_status()
        content = response.json().get("content")
        return COORDINATES.sub("", content).strip() if isinstance(content, str) else None
    except (httpx.HTTPError, ValueError):
        return None
