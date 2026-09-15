"""Verify EVERY registered CrisisWatch endpoint in-process (no live server).

Enumerates the FastAPI OpenAPI schema and drives each route through an
httpx ASGI transport — real HTTP requests/responses, zero server processes.
"""
import asyncio
import json
import re

import httpx

import main as app_main

BASE = "http://test"
OK = []

POST_BODIES = {
    "/api/predict/severity": {
        "event_type": "earthquake",
        "latitude": 37.75,
        "longitude": 140.47,
        "population_density_estimate": 1500,
        "historical_frequency_in_region": 12,
        "source_reliability_score": 0.9,
        "temperature": 28,
        "wind_speed": 40,
        "precipitation": 20,
    },
    "/api/predict/classify": {
        "text": "Severe flooding has displaced thousands of people in Bangladesh after monsoon rains"
    },
    "/api/alerts": {"limit": 2},
    "/api/reports/generate": {"region": "Sindh"},
}

GET_PARAMS = {
    "/api/crises": {"limit": 2},
    "/api/crises/map": {"severity_min": 3},
    "/api/alerts": {"severity_min": 4, "limit": 3},
    "/api/forecast": {"region": "Tohoku", "periods": 10},
    "/api/reports": {"limit": 3},
}


def example_for(schema):
    if not schema:
        return None
    if "example" in schema:
        return schema["example"]
    t = schema.get("type")
    if t == "integer":
        return schema.get("minimum", 0) or 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return True
    if t == "string":
        if schema.get("format") == "date-time":
            return "2026-01-01T00:00:00Z"
        return "earthquake" if "event_type" in str(schema) else "sample"
    if t == "array":
        return []
    if t == "object":
        return {}
    return None


def build_get_params(route, schema):
    params = {}
    for name, prop in (schema.get("query") or {}).items():
        for param in route.parameters:
            if param.get("name") == name and param.get("required"):
                params[name] = example_for(prop)
                break
    return params


async def run():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_main.app), base_url=BASE, timeout=120) as c:
        schema = app_main.app.openapi()
        paths = list(schema["paths"].items())
        print(f"Registered routes: {len(paths)}")
        print("=" * 68)

        # First, fetch real IDs from list endpoints so path-param routes work
        def first_item(payload):
            for key in ("events", "alerts", "reports", "items"):
                val = payload.get(key)
                if isinstance(val, list) and val:
                    return val[0]
            if isinstance(payload, list) and payload:
                return payload[0]
            return None

        real_ids = {}

        async def fetch_list_id(c, param_name):
            """Fetch a fresh real ID for a path-param from its list endpoint."""
            list_route = {
                "crisis_id": "/api/crises",
                "report_id": "/api/reports",
                "alert_id": "/api/alerts",
            }.get(param_name)
            if not list_route:
                return None
            try:
                resp = await c.get(list_route, params={"limit": 1})
                if resp.status_code == 200:
                    item = first_item(resp.json())
                    if item and item.get("id"):
                        return str(item["id"])
            except Exception:
                pass
            return None

        results = []
        for path, ops in paths:
            if path.startswith("/openapi"):
                continue
            for method, op in ops.items():
                method = method.upper()
                if method not in ("GET", "POST", "PATCH", "PUT", "DELETE"):
                    continue

                # Resolve path parameters (lazily, at request time)
                url = path
                for m in re.findall(r"\{(\w+)\}", path):
                    rid = real_ids.get(m) or await fetch_list_id(c, m)
                    if rid:
                        real_ids[m] = rid
                        url = url.replace("{" + m + "}", rid)

                try:
                    if method == "GET":
                        params = {}
                        for p in op.get("parameters") or []:
                            if p.get("in") == "query" and p.get("required"):
                                params[p["name"]] = GET_PARAMS.get(path, {}).get(p["name"], 1)
                        resp = await c.get(url, params=params)
                    else:
                        body = POST_BODIES.get(path)
                        resp = await c.request(method, url, json=body if body else None)
                    results.append((method, path, url, resp.status_code, resp.text))
                except Exception as exc:  # noqa: BLE001
                    results.append((method, path, url, "EXC", repr(exc)))

        for method, orig, _url, code, text in results:
            status = "PASS" if code == 200 else "FAIL"
            suffix = ""
            if code != 200:
                snippet = " ".join(text.split())[:160]
                suffix = f"  -> {snippet}"
            print(f"[{status}] {method:6s} {orig:36s} {code}{suffix}")
            if code == 200:
                OK.append(f"{method} {orig}")

        print("=" * 68)
        print(f"PASSED: {len(OK)}/{len(results)} endpoint calls returned 200")

        health = next((r for r in results if r[1] == "/health"), None)
        if health:
            print("HEALTH:", health[4][:200])


if __name__ == "__main__":
    asyncio.run(run())