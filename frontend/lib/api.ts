import { API_BASE } from "./utils";
import type {
  AlertItem,
  ClassificationResult,
  CrisisEvent,
  CrisisStats,
  ForecastResponse,
  Hotspot,
  RegionInfo,
  Report,
  SeverityPrediction,
} from "./types";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export function getCrises(params?: Record<string, string | number>): Promise<{ total: number; events: CrisisEvent[] }> {
  const qs = params ? `?${new URLSearchParams(String(params as Record<string, string>))}` : "";
  return request(`/api/crises${qs}`);
}

export function getCrisisMap(params?: Record<string, string | number>): Promise<{ features: GeoJSON.Feature[] }> {
  const qs = params ? `?${new URLSearchParams(String(params as Record<string, string>))}` : "";
  return request(`/api/crises/map${qs}`);
}

export function getStats(): Promise<CrisisStats> {
  return request("/api/crises/stats");
}

export function getRegions(): Promise<{ regions: RegionInfo[] }> {
  return request("/api/crises/regions");
}

export function getAlerts(params?: Record<string, string | number>): Promise<{ alerts: AlertItem[]; unread_count: number }> {
  const qs = params ? `?${new URLSearchParams(String(params as Record<string, string>))}` : "";
  return request(`/api/alerts${qs}`);
}

export function predictSeverity(body: Record<string, unknown>): Promise<SeverityPrediction> {
  return request("/api/predict/severity", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function classifyText(text: string): Promise<ClassificationResult> {
  return request("/api/predict/classify", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export function getForecast(params: Record<string, string | number>): Promise<ForecastResponse> {
  const qs = new URLSearchParams(String(params as Record<string, string>));
  return request(`/api/forecast?${qs}`);
}

export function getClusters(): Promise<{ clusters: Hotspot[]; count: number }> {
  return request("/api/clusters");
}

export function generateReport(body: Record<string, unknown>): Promise<Report> {
  return request("/api/reports/generate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getReports(params?: Record<string, string | number>): Promise<{ reports: Report[]; count: number }> {
  const qs = params ? `?${new URLSearchParams(String(params as Record<string, string>))}` : "";
  return request(`/api/reports${qs}`);
}

export function markAlertRead(alertId: string): Promise<{ id: string; is_read: boolean }> {
  return request(`/api/alerts/${alertId}/read`, {
    method: "PATCH",
  });
}