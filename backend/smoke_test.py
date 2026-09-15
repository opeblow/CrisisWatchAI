"""In-process smoke test for all CrisisWatch API endpoints (no live server needed)."""
import asyncio

import httpx

BASE = "http://test"


def out(label, resp):
    body = resp.text
    print(f"--- {label} [{resp.status_code}]")
    if len(body) > 600:
        print(body[:600] + "...")
    else:
        print(body)


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=120) as client:
        import main as app_main

        transport = httpx.ASGITransport(app=app_main.app)
        client = httpx.AsyncClient(transport=transport, base_url=BASE, timeout=120)

        out("health", await client.get("/health"))
        out("stats", await client.get("/api/crises/stats"))

        resp = await client.get("/api/crises?limit=3")
        out("crises", resp)

        out("geojson", await client.get("/api/crises/map?severity_min=3"))

        resp = await client.get("/api/crises/regions")
        out("regions", resp)

        body = {
            "event_type": "earthquake",
            "latitude": 37.75,
            "longitude": 140.47,
            "population_density_estimate": 1500,
            "historical_frequency_in_region": 12,
            "source_reliability_score": 0.9,
            "temperature": 28,
            "wind_speed": 40,
            "precipitation": 20,
        }
        out("predict/severity", await client.post("/api/predict/severity", json=body))

        out("predict/classify", await client.post("/api/predict/classify", json={"text": "Severe flooding has displaced thousands of people in Bangladesh after monsoon rains"}))

        out("forecast", await client.get("/api/forecast?region=Tohoku&periods=30"))

        out("clusters", await client.get("/api/clusters"))
        out("alerts", await client.get("/api/alerts?severity_min=4&limit=3"))

        resp = await client.post("/api/reports/generate", json={"region": "Sindh"})
        out("reports/generate", resp)
        if resp.status_code == 200:
            rid = resp.json()["id"]
            out("reports/get", await client.get(f"/api/reports/{rid}"))

        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())