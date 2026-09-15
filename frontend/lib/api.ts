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

function buildQuery(params?: Record<string, string | number | boolean | undefined>): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.append(key, String(value));
    }
  }
  const q = search.toString();
  return q ? `?${q}` : "";
}

export function getCrises(params?: Record<string, string | number>): Promise<{ total: number; events: CrisisEvent[] }> {
  return request(`/api/crises${buildQuery(params)}`);
}

export function getCrisisMap(params?: Record<string, string | number>): Promise<{ features: GeoJSON.Feature[] }> {
  return request(`/api/crises/map${buildQuery(params)}`);
}

export function getStats(): Promise<CrisisStats> {
  return request("/api/crises/stats");
}

export function getRegions(): Promise<{ regions: RegionInfo[] }> {
  return request("/api/crises/regions");
}

export function getAlerts(params?: Record<string, string | number>): Promise<{ alerts: AlertItem[]; unread_count: number }> {
  return request(`/api/alerts${buildQuery(params)}`);
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
  return request(`/api/forecast${buildQuery(params)}`);
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
  return request(`/api/reports${buildQuery(params)}`);
}

export function markAlertRead(alertId: string): Promise<{ id: string; is_read: boolean }> {
  return request(`/api/alerts/${alertId}/read`, {
    method: "PATCH",
  });
}