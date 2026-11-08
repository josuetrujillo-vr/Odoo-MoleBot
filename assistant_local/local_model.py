"""Minimal local-only Ollama chat transport for the initial PC prototype."""

import ipaddress
import json
import math
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise HTTPError(request.full_url, code, "Redirects are not allowed", headers, fp)


def chat(base_url, model, messages, tools, timeout=30):
    """Send a bounded chat request to an explicitly local loopback service."""
    try:
        url = urlsplit(base_url)
        address = ipaddress.ip_address(url.hostname or "")
        port = url.port
    except (TypeError, ValueError):
        raise ValueError("Expected a loopback HTTP service URL") from None
    if (url.scheme != "http" or not address.is_loopback or not port or url.username or
            url.password or url.path not in ("", "/") or url.query or url.fragment):
        raise ValueError("Expected a loopback HTTP service URL")
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or
            not math.isfinite(timeout) or timeout <= 0 or timeout > 120):
        raise ValueError("Timeout must be between zero and 120 seconds")
    if not isinstance(model, str) or not model.strip() or not isinstance(messages, list) or not isinstance(tools, list):
        raise ValueError("Invalid model request")
    payload = json.dumps({"model": model, "messages": messages, "tools": tools,
                          "stream": False}, ensure_ascii=False).encode("utf-8")
    if len(payload) > 1024 * 1024:
        raise ValueError("Model request exceeds the size limit")
    request = Request(base_url.rstrip("/") + "/api/chat", data=payload,
                      headers={"Content-Type": "application/json"}, method="POST")
    opener = build_opener(ProxyHandler({}), _RejectRedirects())
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Model response exceeds the size limit")
    result = json.loads(raw)
    if not isinstance(result, dict) or not isinstance(result.get("message"), dict):
        raise ValueError("Invalid model response")
    message = result["message"]
    content = message.get("content", "")
    calls = message.get("tool_calls", [])
    if (message.get("role") != "assistant" or not isinstance(content, str) or
            not isinstance(calls, list) or len(calls) > 3):
        raise ValueError("Invalid model message")
    normalized_calls = []
    for call in calls:
        function = call.get("function") if isinstance(call, dict) else None
        if (not isinstance(function, dict) or not isinstance(function.get("name"), str) or
                not function["name"] or not isinstance(function.get("arguments"), dict)):
            raise ValueError("Invalid model tool call")
        normalized_calls.append({"function": {"name": function["name"],
                                               "arguments": function["arguments"]}})
    return {"role": "assistant", "content": content, "tool_calls": normalized_calls}
