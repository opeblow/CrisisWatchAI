"""Seed the CrisisWatch AI database with realistic demo crisis events.

Generates a globally distributed corpus of crisis events spanning the last
~11 months so every dashboard view, ML model, forecast and report has data.
Run from ``backend/``:

    python seed_demo.py
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone

from db.database import AsyncSessionLocal, init_db
from db.models import CrisisAlert, CrisisEvent, CrisisEventType
from services.alert_service import AlertService

random.seed(42)

# (event_type, country, region, lat, lon, base_severity, description)
SAMPLE_EVENTS: list[tuple[str, str, str, float, float, int, str]] = [
    ("earthquake", "Japan", "Fukushima", 37.75, 140.47, 4, "6.3 magnitude earthquake struck off the coast of Fukushima, triggering tsunami advisories for the Tohoku coastline."),
    ("earthquake", "Turkey", "Gaziantep", 37.07, 37.38, 5, "Major 7.8 magnitude earthquake devastated southern Turkey, with thousands of aftershocks and widespread building collapse."),
    ("earthquake", "Indonesia", "Java", -7.25, 110.40, 4, "5.9 magnitude quake shook Central Java; landslides cut off rural communities east of Yogyakarta."),
    ("flood", "Bangladesh", "Sylhet", 24.90, 91.87, 4, "Monsoon floods submerged large parts of Sylhet division, displacing over 400,000 people."),
    ("flood", "Pakistan", "Sindh", 25.89, 68.42, 5, "Catastrophic flooding across Sindh province impacted millions; agricultural land inundated for weeks."),
    ("flood", "India", "Assam", 26.20, 92.94, 3, "Brahmaputra river burst its banks following heavy rainfall, affecting low-lying districts."),
    ("cyclone", "Philippines", "Leyte", 11.00, 124.99, 4, "Typhoon made landfall over Leyte with 190 km/h winds, causing storm surges and power outages."),
    ("cyclone", "Mozambique", "Sofala", -19.84, 34.89, 5, "Category 4 cyclone tore through Beira corridor, bringing torrential rains and flash flooding."),
    ("cyclone", "United States", "Florida", 27.98, -81.96, 3, "Hurricane reached the Florida coast with sustained winds of 130 mph, triggering mass evacuations."),
    ("drought", "Somalia", "Bay", 3.12, 43.65, 4, "Extended drought has devastated harvests across Bay region; 6.9 million people facing acute food insecurity."),
    ("drought", "Ethiopia", "Afar", 11.75, 40.95, 4, "Severe dry spell continues in the Afar region, killing livestock and shrinking water sources."),
    ("drought", "Brazil", "Amazonas", -3.07, -61.66, 3, "Record-low river levels on the Negro River strand riverine communities reliant on boat transport."),
    ("wildfire", "Canada", "British Columbia", 50.12, -122.95, 4, "Out-of-control wildfires forced evacuation orders across the Okanagan Valley; air quality hazardous."),
    ("wildfire", "Greece", "Attica", 38.05, 23.80, 3, "Fast-moving brush fires threatened northern Athens suburbs amid a prolonged heatwave."),
    ("wildfire", "Australia", "New South Wales", -33.87, 151.21, 3, "Bushfire emergency declared across Greater Sydney due to dry conditions and high winds."),
    ("epidemic", "Democratic Republic of the Congo", "North Kivu", -1.35, 29.23, 4, "New Ebola cluster reported in North Kivu; teams deployed for ring vaccination."),
    ("epidemic", "Uganda", "Kampala", 0.35, 32.58, 3, "Cholera outbreak in urban Kampala linked to contaminated water sources; 300+ cases."),
    ("epidemic", "Yemen", "Sanaa", 15.37, 44.19, 4, "Cholera resurgence in Sanaa as water infrastructure collapses amid ongoing conflict."),
    ("conflict", "Ukraine", "Kharkiv Oblast", 49.99, 36.23, 5, "Intense artillery shelling continued in Kharkiv; civilian infrastructure repeatedly struck."),
    ("conflict", "Sudan", "Khartoum", 15.50, 32.56, 5, "Fighting between rival forces persists in Khartoum, trapping civilians and disrupting aid."),
    ("conflict", "Myanmar", "Rakhine", 20.15, 92.90, 4, "Armed clashes intensified in Rakhine, forcing displacement across the border region."),
    ("displacement", "South Sudan", "Upper Nile", 9.77, 32.11, 4, "Renewed intercommunal violence displaced tens of thousands toward the Nile corridor."),
    ("displacement", "Syria", "Idlib", 35.93, 36.63, 5, "Renewed escalation sent thousands of families fleeing toward the Turkish border crossing."),
    ("displacement", "Venezuela", "Miranda", 10.25, -66.79, 3, "Humanitarian crisis continues to drive out-migration; shelters report rising arrivals."),
]

# Extra pure-region names so forecasting/clustering have coherent hot zones.
REGION_ALIASES = {
    "Fukushima": "Tohoku",
    "Gaziantep": "Southeastern Anatolia",
    "Java": "Central Java",
    "Sylhet": "Sylhet",
    "Sindh": "Sindh",
    "Assam": "Assam",
    "Leyte": "Eastern Visayas",
    "Sofala": "Sofala",
    "Florida": "Southeast US",
    "Bay": "Bay",
    "Afar": "Afar",
    "Amazonas": "Western Amazon",
    "British Columbia": "Western Canada",
    "Attica": "Attica",
    "New South Wales": "Southeast Australia",
    "North Kivu": "North Kivu",
    "Kampala": "Central Uganda",
    "Sanaa": "Sanaa",
    "Kharkiv Oblast": "Eastern Ukraine",
    "Khartoum": "Khartoum",
    "Rakhine": "Rakhine",
    "Upper Nile": "Upper Nile",
    "Idlib": "Northwest Syria",
    "Miranda": "Central Venezuela",
}


def _issue_amount(multiplier: int, noise: float) -> int:
    base = int(1000 * multiplier * random.uniform(0.7, 1.3))
    if random.random() < 1 - noise:
        return base
    return max(0, int(base * random.uniform(0.1, 0.5)))


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(__import__("sqlalchemy").select(CrisisEvent.id))).scalars().first()
        if existing:
            print("Database already seeded — skipping.")
            return

        now = datetime.now(timezone.utc)
        events = []
        for base in SAMPLE_EVENTS:
            event_type, country, region, lat, lon, sev, desc = base
            region = REGION_ALIASES.get(region, region)
            for _ in range(random.randint(8, 14)):
                offset_days = random.randint(5, 330)
                ts = now - timedelta(days=offset_days, hours=random.randint(0, 23))
                level = max(1, min(5, sev + random.choice([-1, 0, 0, 1])))
                casualties = _issue_amount(3 if level >= 4 else 1, 0.6)
                displaced = _issue_amount(8 if level >= 4 else 3, 0.5)
                affected = _issue_amount(15 if level >= 4 else 6, 0.4)
                events.append(
                    CrisisEvent(
                        source="demo_seed",
                        event_type=event_type,
                        title=f"{event_type.title()} — {region}",
                        description=desc,
                        severity=level,
                        latitude=lat + random.uniform(-0.8, 0.8),
                        longitude=lon + random.uniform(-0.8, 0.8),
                        country=country,
                        region=region,
                        timestamp=ts,
                        casualties=casualties,
                        displaced=displaced,
                        affected=affected,
                    )
                )
        session.add_all(events)
        await session.commit()
        print(f"Seeded {len(events)} crisis events.")

        ids = (await session.execute(__import__("sqlalchemy").select(CrisisEvent.id, CrisisEvent.severity))).all()
        svc = AlertService(session)
        created = 0
        for eid, sev in ids:
            if sev < 4:
                continue
            ev = (await session.get(CrisisEvent, eid))
            session.add(
                CrisisAlert(
                    crisis_event_id=eid,
                    severity=sev,
                    message=svc.generate_alert_message(ev),
                    is_read=random.random() < 0.4,
                )
            )
            created += 1
        await session.commit()
        print(f"Created {created} alerts.")


if __name__ == "__main__":
    asyncio.run(main())