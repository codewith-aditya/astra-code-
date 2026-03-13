"""Tool: web_fetch -- Fetch content from a URL."""

from __future__ import annotations

import urllib.request
import urllib.error

from astra.tools.registry import ToolDefinition


def handle_web_fetch(
    url: str,
    max_length: int = 10000,
) -> dict:
    """Fetch content from a URL and return as text."""
    if not url.startswith(("http://", "https://")):
        return {"error": "URL must start with http:// or https://"}

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Astra-Agent/0.1"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(max_length)

            encoding = "utf-8"
            if "charset=" in content_type:
                encoding = content_type.split("charset=")[-1].split(";")[0].strip()

            text = raw.decode(encoding, errors="replace")

    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}: {exc.reason}"}
    except urllib.error.URLError as exc:
        return {"error": f"URL error: {exc.reason}"}
    except Exception as exc:
        return {"error": f"Fetch failed: {exc}"}

    return {
        "url": url,
        "content_type": content_type,
        "length": len(text),
        "content": text[:max_length],
    }


WEB_FETCH_TOOL = ToolDefinition(
    name="web_fetch",
    description="Fetch content from a URL and return it as text.",
    parameters={
        "url": {
            "type": "string",
            "description": "The URL to fetch (must start with http/https).",
        },
        "max_length": {
            "type": "integer",
            "description": "Max characters to return. Default 10000.",
            "optional": True,
        },
    },
    handler=handle_web_fetch,
)
