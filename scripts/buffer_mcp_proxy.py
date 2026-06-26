#!/usr/bin/env python3
"""
Buffer MCP HTTP-to-Stdio Proxy
 Bridges OpenClaw's stdio-based MCP to Buffer's HTTP MCP endpoint.
 Usage: python3 buffer_mcp_proxy.py
 (OpenClaw invokes it as an MCP server via stdio)
"""

import sys
import json
import urllib.request
import urllib.error

BUFFER_TOKEN = "AXIGAfnblQ7bv-0dtXwtXzwNGoj9aRNctYaM6EXV1A0"
BUFFER_URL = "https://mcp.buffer.com/mcp"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "Authorization": f"Bearer {BUFFER_TOKEN}",
}


def call_buffer(method, params=None):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BUFFER_URL, data=data, headers=HEADERS, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            # Try SSE format first (data: {...}\n\n)
            for line in raw.split("\n"):
                if line.startswith("data: "):
                    return json.loads(line[6:])
            # Fall back to plain JSON
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        # Buffer MCP may return 406 but still include valid JSON-RPC in body
        try:
            for line in body.split("\n"):
                if line.startswith("data: "):
                    return json.loads(line[6:])
            return json.loads(body)
        except Exception:
            return {"jsonrpc": "2.0", "error": {"code": e.code, "message": body}}
    except Exception as e:
        return {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}}


def main():
    """
    Read JSON-RPC requests from stdin, forward to Buffer HTTP MCP,
    write responses to stdout.
    """
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = request.get("method", "")
        params = request.get("params")
        req_id = request.get("id")

        # Handle batch or single
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "buffer-mcp-proxy", "version": "1.0"},
            }
            resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
            print(json.dumps(resp), flush=True)

        elif method == "tools/list":
            result = call_buffer("tools/list", params)
            # Buffer returns {"tools": [...]} directly for tools/list
            resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
            print(json.dumps(resp), flush=True)

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            # Buffer MCP requires tools/call as the HTTP method, with tool name + args as params
            raw_result = call_buffer("tools/call", {"name": tool_name, "arguments": arguments})
            # Buffer wraps tool results in {"content":[{"type":"text","text":"...json..."}]}
            # Unwrap one layer: raw_result is the full JSON-RPC response {"result":{...}}
            result = raw_result.get("result", raw_result)
            if isinstance(result, dict) and "content" in result:
                content = result["content"]
                if isinstance(content, list) and len(content) > 0:
                    item = content[0]
                    if isinstance(item, dict) and "text" in item:
                        try:
                            result = json.loads(item["text"])
                        except (json.JSONDecodeError, TypeError):
                            pass  # keep as-is
            resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
            print(json.dumps(resp), flush=True)

        else:
            # Forward unknown methods as-is
            result = call_buffer(method, params)
            resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
            print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    main()
