"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { BrainCircuit, Loader2, Sparkles, TrendingUp } from "lucide-react";
import Card, { CardContent, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Select } from "@/components/ui/Select";
import Skeleton from "@/components/ui/Skeleton";
import SeverityGauge from "@/components/SeverityGauge";
import CrisisMap from "@/components/CrisisMap";
import { ForecastChart } from "@/components/TrendChart";
import { classifyText, getClusters, getForecast, getRegions, predictSeverity } from "@/lib/api";
import { EVENT_TYPE_LABELS, SEVERITY_COLORS } from "@/lib/utils";
import type { ShapFeature } from "@/lib/types";

export default function PredictionsPage() {
  const [region, setRegion] = useState("");
  const [periods, setPeriods] = useState("12");
  const [running, setRunning] = useState(false);
  const [predResult, setPredResult] = useState<any>(null);
  const [predError, setPredError] = useState<string | null>(null);
  const [nlpResult, setNlpResult] = useState<any>(null);
  const [nlpText, setNlpText] = useState("Monsoon floods have displaced thousands of families in Bangladesh");

  const { data: regions } = useQuery({ queryKey: ["regions"], queryFn: getRegions });
  const { data: clusters } = useQuery({ queryKey: ["clusters"], queryFn: getClusters });
  const selectedRegion = region || regions?.regions?.[0]?.region || "";

  const { data: forecast, isLoading: forecastLoading } = useQuery({
    queryKey: ["forecast", selectedRegion, periods],
    queryFn: () => getForecast({ region: selectedRegion, periods: Number(periods), freq: "W" }),
    enabled: Boolean(selectedRegion),
  });

  const hotspotEvents = useMemo(() => {
    if (!clusters?.clusters?.length) return [];
    return clusters.clusters.map((c) => ({
      id: `cluster-${c.cluster_id}`,
      source: "hdbscan",
      event_type: "displacement",
      title: `Hotspot #${c.cluster_id + 1} — ${Math.round(c.risk_score * 100)}% risk`,
      description: "Spatial cluster of active crisis events identified by density and severity.",
      severity: Math.min(5, Math.max(1, Math.round(c.avg_severity))),
      severity_label: "",
      latitude: c.center_lat,
      longitude: c.center_lon,
      country: "",
      region: selectedRegion,
      timestamp: null,
      casualties: null,
      displaced: null,
      affected: c.event_count,
    }));
  }, [clusters, selectedRegion]);

  async function runSeverityPrediction() {
    setRunning(true);
    setPredError(null);
    setPredResult(null);
    try {
      const res = await predictSeverity({
        event_type: "earthquake",
        latitude: 37.75,
        longitude: 140.47,
        population_density_estimate: 1500,
        historical_frequency_in_region: 12,
        source_reliability_score: 0.9,
        temperature: 28,
        wind_speed: 40,
        precipitation: 20,
      });
      setPredResult(res);
    } catch (err) {
      setPredError(err instanceof Error ? err.message : "Prediction failed");
    } finally {
      setRunning(false);
    }
  }

  async function runNLP() {
    setNlpResult(null);
    try {
      setNlpResult(await classifyText(nlpText));
    } catch (err) {
      setPredError(err instanceof Error ? err.message : "Classification failed");
    }
  }

  const regionOptions = [
    { value: "", label: "Choose a region…" },
    ...(regions?.regions?.slice(0, 20) ?? []).map((r) => ({ value: r.region, label: `${r.region} (${r.count})` })),
  ];

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-zinc-900">
          <BrainCircuit className="h-6 w-6 text-yellow-600" /> ML Predictions
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Four models working together — XGBoost severity classification, DistilBERT NLP, Prophet forecasting and HDBSCAN clustering. Every result is explainable.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
          <Card className="h-full">
            <CardHeader
              title="Severity Classifier"
              subtitle="XGBoost · 5-level risk rating"
              action={<Badge color="#FACC15">AI</Badge>}
            />
            <CardContent>
              <div className="flex flex-col items-center gap-4">
                <p className="text-center text-xs leading-relaxed text-zinc-500">
                  Predict the severity of a new in-progress crisis event and see exactly
                  which features drove the decision (SHAP attribution).
                </p>
                <Button onClick={runSeverityPrediction} disabled={running}>
                  {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  {running ? "Analyzing…" : "Predict severity"}
                </Button>
                {predError && <p className="text-xs text-red-600">{predError}</p>}
                {predResult && (
                  <div className="flex flex-col items-center gap-3">
                    <SeverityGauge severity={predResult.prediction.severity} size={130} />
                    <div className="text-xs text-zinc-500">
                      Confidence{" "}
                      <strong className="text-zinc-900">
                        {(predResult.prediction.confidence * 100).toFixed(1)}%
                      </strong>
                    </div>
                    {predResult.shap_values?.top_features?.length > 0 && (
                      <div className="w-full rounded-xl bg-zinc-50 p-3">
                        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                          Why this prediction?
                        </div>
                        <div className="space-y-1.5">
                          {predResult.shap_values.top_features.map((f: ShapFeature) => (
                            <div key={f.feature_name} className="flex items-center justify-between text-xs">
                              <span className="text-zinc-500">{f.feature_name.replace("_", " ")}</span>
                              <span
                                className="font-mono"
                                style={{ color: "#a16207" }}
                              >
                                {f.direction === "increases" ? "+" : ""}
                                {f.shap_value}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {predResult.explanation && (
                      <p className="text-xs italic leading-relaxed text-zinc-500">
                        {predResult.explanation}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0, transition: { delay: 0.1 } }}>
          <Card className="h-full">
            <CardHeader
              title="NLP Report Classifier"
              subtitle="DistilBERT · 8 crisis categories"
              action={<Badge color="#EAB308">TEXT</Badge>}
            />
            <CardContent>
              <textarea
                value={nlpText}
                onChange={(e) => setNlpText(e.target.value)}
                rows={5}
                className="w-full resize-none rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-900 outline-none focus:border-gold"
                placeholder="Paste an incoming situation report…"
              />
              <Button className="mt-3" onClick={runNLP}>
                <Sparkles className="h-4 w-4" /> Classify report
              </Button>
              {nlpResult && (
                <div className="mt-3 space-y-2">
                  <div className="flex flex-wrap gap-2">
                    {nlpResult.labels.map((l: string, i: number) => (
                      <span
                        key={l}
                        className="rounded-full px-3 py-1 text-xs font-semibold"
                        style={{
                          backgroundColor: `${SEVERITY_COLORS[(i % 5) + 1] ?? "#FACC15"}22`,
                          color: SEVERITY_COLORS[(i % 5) + 1] ?? "#FACC15",
                          border: `1px solid ${SEVERITY_COLORS[(i % 5) + 1] ?? "#FACC15"}55`,
                        }}
                      >
                        {l} {Math.round(nlpResult.scores[i] * 100)}%
                      </span>
                    ))}
                  </div>
                  <p className="text-xs text-zinc-500">
                    Primary: <strong className="text-zinc-900">{nlpResult.primary_label}</strong>
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0, transition: { delay: 0.2 } }}>
          <Card className="h-full">
            <CardHeader
              title="Hotspot Clustering"
              subtitle="HDBSCAN · crisis zones by density"
              action={<Badge color="#FACC15">{clusters?.count ?? "…"}</Badge>}
            />
            <CardContent>
              <p className="text-xs leading-relaxed text-zinc-500">
                Spatial hotspots currently detected across active crisis events, ranked by a
                composite risk score of density + average severity.
              </p>
              <div className="mt-3 space-y-2">
                {(clusters?.clusters ?? []).slice(0, 6).map((c) => (
                  <div
                    key={c.cluster_id}
                    className="flex items-center justify-between rounded-lg bg-zinc-50 px-3 py-2 text-xs"
                  >
                    <span className="text-zinc-600">
                      <span className="font-semibold text-zinc-900">#{c.cluster_id + 1}</span> ·{" "}
                      {c.center_lat.toFixed(1)}, {c.center_lon.toFixed(1)}
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="text-zinc-500">{c.event_count} events</span>
                      <span className="font-mono" style={{ color: SEVERITY_COLORS[Math.ceil(c.avg_severity)] ?? "#94a3b8" }}>
                        {(c.risk_score * 100).toFixed(0)}%
                      </span>
                    </span>
                  </div>
                ))}
                {!clusters?.clusters?.length && <p className="text-xs text-zinc-500">No hotspots yet.</p>}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      <Card>
        <CardHeader
          title="Regional Forecast"
          subtitle="Prophet time-series · predicted crisis events with 95% confidence intervals"
          action={
            <div className="flex items-center gap-3">
              <Select value={region} onChange={setRegion} options={regionOptions} className="w-56" label="" />
              <Select value={periods} onChange={setPeriods} options={[{ value: "12", label: "12 weeks" }, { value: "26", label: "26 weeks" }, { value: "52", label: "52 weeks" }]} className="w-36" label="" />
            </div>
          }
        />
        <CardContent>
          {!selectedRegion ? (
            <Skeleton className="h-[300px]" />
          ) : forecastLoading ? (
            <Skeleton className="h-[300px]" />
          ) : (
            <>
              <ForecastChart points={forecast?.points ?? []} />
              <div className="mt-2 flex items-center gap-2 text-xs text-zinc-500">
                <TrendingUp className="h-4 w-4" />
                {forecast?.model ?? "Forecast"} · region <strong className="text-zinc-900">{selectedRegion}</strong>
                {forecast?.metrics && JSON.stringify(forecast.metrics).slice(0, 80)}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader title="Forecast Regions on Map" subtitle="Predicted hotspot locations by density risk" />
        <CardContent className="p-0">
          {hotspotEvents.length ? (
            <CrisisMap events={hotspotEvents} height="h-[360px]" />
          ) : (
            <Skeleton className="m-4 h-[320px]" />
          )}
        </CardContent>
      </Card>

      <p className="pb-4 text-center text-[11px] text-zinc-500">
        XGBoost v1 · DistilBERT fine-tuned (fallback: keyword model) · Prophet (fallback: seasonal-naive) · HDBSCAN (fallback: DBSCAN)
      </p>
    </div>
  );
}