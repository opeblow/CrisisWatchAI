"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { SEVERITY_COLORS, SEVERITY_LABELS, EVENT_TYPE_LABELS, timeAgo } from "@/lib/utils";
import type { CrisisEvent } from "@/lib/types";

const MapContainer = dynamic(
  () => import("react-leaflet").then((m) => m.MapContainer),
  { ssr: false }
);
const TileLayer = dynamic(() => import("react-leaflet").then((m) => m.TileLayer), {
  ssr: false,
});
const CircleMarker = dynamic(
  () => import("react-leaflet").then((m) => m.CircleMarker),
  { ssr: false }
);
const Popup = dynamic(() => import("react-leaflet").then((m) => m.Popup), {
  ssr: false,
});

function markerRadius(severity: number): number {
  return 5 + severity * 3;
}

function MarkerLayer({ events }: { events: CrisisEvent[] }) {
  return (
    <>
      {events.map((e) => {
        const color = SEVERITY_COLORS[e.severity] ?? "#94a3b8";
        return (
          <CircleMarker
            key={e.id}
            center={[e.latitude, e.longitude]}
            radius={markerRadius(e.severity)}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: 0.55,
              weight: 1,
            }}
          >
            <Popup>
              <div style={{ minWidth: 200 }}>
                <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1, color: color, fontWeight: 700 }}>
                  {EVENT_TYPE_LABELS[e.event_type] ?? e.event_type} · {SEVERITY_LABELS[e.severity]}
                </div>
                <div style={{ fontWeight: 600, margin: "4px 0" }}>{e.title}</div>
                <div style={{ fontSize: 12, opacity: 0.8 }}>{e.region}, {e.country}</div>
                <div style={{ fontSize: 12, opacity: 0.7 }}>{timeAgo(e.timestamp)}</div>
                <div style={{ fontSize: 12, marginTop: 4, opacity: 0.75 }}>
                  {e.affected ? `${e.affected.toLocaleString()} affected · ` : ""}
                  {e.displaced ? `${e.displaced.toLocaleString()} displaced` : ""}
                </div>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </>
  );
}

export default function CrisisMap({
  events,
  height = "h-[480px]",
}: {
  events: CrisisEvent[];
  height?: string;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const bounds = useMemo(() => {
    if (!events.length) return null;
    const lats = events.map((e) => e.latitude);
    const lons = events.map((e) => e.longitude);
    return [
      [Math.min(...lats) - 5, Math.min(...lons) - 5],
      [Math.max(...lats) + 5, Math.max(...lons) + 5],
    ] as [[number, number], [number, number]];
  }, [events]);

  if (!mounted) return <div className={`${height} w-full rounded-2xl bg-slate-900/40 animate-pulse`} />;

  return (
    <div className={`${height} w-full overflow-hidden rounded-2xl border border-white/10`}>
      <MapContainer
        center={[20, 0]}
        zoom={2}
        bounds={bounds ?? undefined}
        boundsOptions={{ padding: [20, 20] }}
        style={{ height: "100%", width: "100%" }}
        scrollWheelZoom
      >
        <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" attribution="&copy; OpenStreetMap &copy; CARTO" />
        <MarkerLayer events={events} />
      </MapContainer>
    </div>
  );
}