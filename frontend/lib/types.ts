export interface CrisisEvent {
  id: string;
  source: string;
  event_type: string;
  title: string;
  description: string;
  severity: number;
  severity_label: string;
  latitude: number;
  longitude: number;
  country: string;
  region: string;
  timestamp: string | null;
  casualties: number | null;
  displaced: number | null;
  affected: number | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
}

export interface CrisisStats {
  total_events: number;
  active_last_30d: number;
  countries_impacted: number;
  critical_ongoing: number;
  by_type: Record<string, number>;
  by_severity: Record<number, number>;
  top_countries: { country: string; count: number }[];
}

export interface AlertItem {
  id: string;
  crisis_event_id: string;
  severity: number;
  severity_label: string;
  severity_color: string;
  message: string;
  is_read: boolean;
  created_at: string | null;
  event: {
    event_type: string | null;
    title: string | null;
    country: string | null;
    region: string | null;
    latitude: number | null;
    longitude: number | null;
    timestamp: string | null;
  } | null;
}

export interface ShapFeature {
  feature_name: string;
  value: number;
  shap_value: number;
  direction: "increases" | "decreases";
}

export interface SeverityPrediction {
  prediction: {
    severity: number;
    severity_label: string;
    confidence: number;
    probabilities: Record<string, number>;
  };
  shap_values: {
    predicted_severity: number;
    class_name: string;
    top_features: ShapFeature[];
    text: string;
  };
  explanation: string;
}

export interface ClassificationResult {
  labels: string[];
  scores: number[];
  primary_label: string;
  primary_score: number;
  text: string;
}

export interface ForecastPoint {
  ds: string;
  yhat: number;
  yhat_lower: number;
  yhat_upper: number;
  group: string;
}

export interface ForecastResponse {
  region: string;
  crisis_type: string;
  periods: number;
  freq: string;
  model: string;
  points: ForecastPoint[];
  metrics: Record<string, unknown>;
}

export interface Hotspot {
  cluster_id: number;
  center_lat: number;
  center_lon: number;
  event_count: number;
  avg_severity: number;
  risk_score: number;
}

export interface RegionInfo {
  region: string;
  count: number;
  max_severity: number;
}

export interface Report {
  id: string;
  region: string;
  date_from: string;
  date_to: string;
  content: string;
  format: string;
  created_at: string;
}