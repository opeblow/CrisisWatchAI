"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Download, FileText, Loader2, PlusCircle } from "lucide-react";
import Card, { CardContent, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Select } from "@/components/ui/Select";
import Skeleton from "@/components/ui/Skeleton";
import { generateReport, getRegions, getReports } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import type { Report } from "@/lib/types";

const DAYS = [
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days (default)" },
  { value: "180", label: "Last 6 months" },
  { value: "365", label: "Last 12 months" },
];

function renderFmt(report: Report) {
  const clean = report.content.replace(/^#+\s+/gm, "");
  return clean
    .split("\n")
    .map((line) => `<p>${line.trim()}</p>`)
    .join("");
}

export default function ReportsPage() {
  const [region, setRegion] = useState("");
  const [days, setDays] = useState("90");
  const [includePred, setIncludePred] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const qc = useQueryClient();

  const { data: regions } = useQuery({ queryKey: ["regions"], queryFn: getRegions });
  const { data: list, isLoading } = useQuery({
    queryKey: ["reports"],
    queryFn: () => getReports(),
  });

  const regionOptions = [
    { value: "", label: "Choose a region…" },
    ...(regions?.regions?.slice(0, 25) ?? []).map((r) => ({ value: r.region, label: `${r.region} (${r.count})` })),
  ];

  async function handleGenerate() {
    if (!region) return;
    setGenerating(true);
    setGenError(null);
    const from = new Date();
    from.setDate(from.getDate() - Number(days));
    try {
      await generateReport({
        region,
        date_from: from.toISOString(),
        format: "markdown",
        include_predictions: includePred,
      });
      qc.invalidateQueries({ queryKey: ["reports"] });
    } catch (err) {
      setGenError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  const latest = useMemo(() => list?.reports?.[0] ?? null, [list]);

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
          <FileText className="h-6 w-6 text-green-400" /> Impact Reports
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Auto-generated situational reports combining real events, ML forecasts and risk
          summaries — ready for briefing decks.
        </p>
      </div>

      <Card>
        <CardHeader
          title="Generate New Report"
          subtitle="Pick a region and a timeframe — the pipeline does the rest"
        />
        <CardContent>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <Select value={region} onChange={setRegion} options={regionOptions} label="Region" />
            <Select value={days} onChange={setDays} options={DAYS} label="Timeframe" />
            <div className="flex items-end gap-3">
              <label className="flex items-center gap-2 rounded-xl border border-white/15 px-4 py-3 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={includePred}
                  onChange={(e) => setIncludePred(e.target.checked)}
                  className="h-4 w-4 accent-blue-500"
                />
                Include ML predictions
              </label>
              <Button onClick={handleGenerate} disabled={!region || generating}>
                {generating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <PlusCircle className="h-4 w-4" />
                )}
                {generating ? "Generating…" : "Generate"}
              </Button>
            </div>
          </div>
          {genError && (
            <p className="mt-3 rounded-lg border border-red-400/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
              {genError}
            </p>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader
            title={latest ? `Latest: ${latest.region}` : "Latest Report"}
            subtitle={latest ? `Generated ${timeAgo(latest.created_at)}` : "No reports generated yet"}
            action={latest ? <Badge color="#22c55e">{latest.format}</Badge> : undefined}
          />
          <CardContent>
            {latest ? (
              <div className="max-h-[480px] overflow-y-auto rounded-xl bg-white/[0.03] p-5">
                <div
                  className="markdown-report"
                  dangerouslySetInnerHTML={{ __html: renderFmt(latest) }}
                />
              </div>
            ) : (
              <Skeleton className="h-[400px]" />
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="Report Archive"
            subtitle="Previously generated"
            action={
              latest ? (
                <a
                  href={`data:text/markdown;charset=utf-8,${encodeURIComponent(latest.content)}`}
                  download={`crisiswatch-report-${latest.region}.md`}
                >
                  <Button variant="outline" size="sm">
                    <Download className="h-3.5 w-3.5" /> Export
                  </Button>
                </a>
              ) : undefined
            }
          />
          <CardContent className="space-y-2">
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16" />)
            ) : (list?.reports ?? []).length === 0 ? (
              <p className="py-10 text-center text-sm text-slate-500">No reports yet — generate one.</p>
            ) : (
              (list?.reports ?? []).map((r, i) => (
                <motion.div
                  key={r.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03 }}
                  className={`rounded-xl border p-3 ${
                    i === 0 ? "border-blue-400/30 bg-blue-500/5" : "border-white/10 bg-white/[0.03]"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-white">{r.region}</span>
                    <Badge color="#22c55e">{r.format}</Badge>
                  </div>
                  <div className="mt-1 flex items-center justify-between text-xs text-slate-500">
                    <span>
                      {r.date_from?.slice(0, 10)} → {r.date_to?.slice(0, 10)}
                    </span>
                    <span>{timeAgo(r.created_at)}</span>
                  </div>
                  <div className="mt-2 line-clamp-2 text-xs text-slate-400">
                    {r.content.replace(/[#*`>\-]/g, "").slice(0, 140)}
                  </div>
                </motion.div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}