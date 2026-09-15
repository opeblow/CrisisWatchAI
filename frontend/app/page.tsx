"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BellRing,
  FileText,
  Gauge,
  Globe,
  LineChart,
  Radar,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { getStats } from "@/lib/api";
import { formatNumber } from "@/lib/utils";

const GOLD = "#FACC15";

function LiveStat({
  label,
  value,
  loading,
  emphasis = false,
}: {
  label: string;
  value: number | null;
  loading: boolean;
  emphasis?: boolean;
}) {
  return (
    <div
      className={`flex flex-col items-center rounded-2xl border px-6 py-5 ${
        emphasis
          ? "border-gold/60 bg-gold/10"
          : "border-zinc-200 bg-zinc-50"
      }`}
    >
      <div
        className={`text-3xl font-extrabold tracking-tight md:text-4xl ${
          emphasis ? "text-yellow-600" : "text-zinc-900"
        }`}
      >
        {loading ? "—" : value != null ? formatNumber(value) : "—"}
      </div>
      <div className="mt-1 text-xs font-medium uppercase tracking-widest text-zinc-500">
        {label}
      </div>
    </div>
  );
}

export default function LandingPage() {
  const { data, isLoading } = useQuery({ queryKey: ["stats"], queryFn: getStats });

  const pillars = [
    {
      icon: ScanSearch,
      color: GOLD,
      title: "Always Watching",
      desc: "Earthquakes, cyclones, floods, wildfires, droughts, epidemics, displacement and conflict — ingested in real time from 7+ public feeds, 24/7.",
    },
    {
      icon: TrendingUp,
      color: "#52525b",
      title: "Think Like an Analyst",
      desc: "Four ML models interpret the noise: XGBoost rates severity, DistilBERT reads reports, Prophet forecasts what comes next, HDBSCAN finds where it clusters.",
    },
    {
      icon: ShieldCheck,
      color: GOLD,
      title: "Explain Every Decision",
      desc: "AI you can audit. Every prediction shows its top contributing features in plain language — no black boxes in a command room.",
    },
    {
      icon: BellRing,
      color: "#52525b",
      title: "Arrest Attention",
      desc: "Priority-ranked alerts hit the moment an event crosses the severity threshold — ranked the way an ops center ranks them.",
    },
  ];

  const models = [
    {
      name: "Severity Classifier",
      model: "XGBoost",
      metric: "97.7% confidence",
      desc: "Rates any in-progress event on a unified 1–5 risk scale using 7+ contextual features, backed by SHAP attribution.",
      icon: Gauge,
      accent: GOLD,
    },
    {
      name: "Situation Report NLP",
      model: "DistilBERT",
      metric: "8 categories",
      desc: "Classifies incoming text reports into crisis types instantly — auto-tagging field notes and news wire copy.",
      icon: FileText,
      accent: "#52525b",
    },
    {
      name: "Regional Forecaster",
      model: "Prophet",
      metric: "95% intervals",
      desc: "Panels next weeks of crisis frequency per region with confidence bands so logistics can preposition resources.",
      icon: LineChart,
      accent: GOLD,
    },
    {
      name: "Hotspot Clustering",
      model: "HDBSCAN",
      metric: "risk-scored",
      desc: "Spots emerging crisis zones by density and severity — the difference between reacting and getting there first.",
      icon: Radar,
      accent: "#52525b",
    },
  ];

  return (
    <div className="relative min-h-screen overflow-x-clip bg-white text-zinc-900">
      {/* Nav */}
      <header className="sticky top-0 z-40 border-b border-zinc-200 bg-white/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gold text-black">
              <Activity className="h-6 w-6" />
            </div>
            <div>
              <div className="text-base font-extrabold tracking-tight text-zinc-900">
                CrisisWatch <span className="text-yellow-600">AI</span>
              </div>
              <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-500">
                Global Intelligence
              </div>
            </div>
          </Link>
          <nav className="hidden items-center gap-6 text-sm font-medium text-zinc-600 md:flex">
            <a href="#features" className="transition-colors hover:text-yellow-600">Features</a>
            <a href="#models" className="transition-colors hover:text-yellow-600">Intelligence</a>
            <a href="#alerts" className="transition-colors hover:text-yellow-600">Alerts</a>
            <a href="#open" className="transition-colors hover:text-yellow-600">Open Access</a>
          </nav>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-xl bg-gold px-5 py-2.5 text-sm font-bold text-black transition-colors hover:bg-lemon"
          >
            Open Dashboard <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="relative mx-auto max-w-7xl px-6 pt-20 pb-16 text-center md:pt-28">
        <div className="pointer-events-none absolute inset-0 -z-10">
          <div className="absolute left-1/2 top-0 h-[500px] w-[900px] -translate-x-1/2 rounded-full bg-yellow-400/10 blur-[120px]" />
          <div className="absolute right-0 top-40 h-72 w-72 rounded-full bg-zinc-200/50 blur-[100px]" />
        </div>

        <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-gold/70 bg-gold/15 px-4 py-1.5 text-xs font-semibold text-yellow-700">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-yellow-500 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-yellow-500" />
          </span>
          Live · tracking {data?.total_events ? formatNumber(data.total_events) : "—"} events across{" "}
          {data?.countries_impacted ? formatNumber(data.countries_impacted) : "—"} countries
        </div>

        <h1 className="mx-auto max-w-4xl text-5xl font-extrabold leading-[1.05] tracking-tight text-zinc-900 md:text-7xl">
          Turn scattered crisis data into{" "}
          <span className="text-yellow-600">life-saving action</span>
        </h1>

        <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-zinc-500">
          One explainable intelligence layer on top of every disaster feed on Earth. COVID
          outbreaks, floods, earthquakes, conflict — aggregated, scored, forecast and delivered
          before it&apos;s too late.
        </p>

        <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
          <Link
            href="/dashboard"
            className="group inline-flex items-center gap-2 rounded-2xl bg-gold px-8 py-4 text-base font-bold text-black transition-colors hover:bg-lemon"
          >
            Enter the Dashboard
            <ArrowRight className="h-5 w-5 transition-transform group-hover:translate-x-1" />
          </Link>
          <Link
            href="/predictions"
            className="inline-flex items-center gap-2 rounded-2xl border border-zinc-300 px-8 py-4 text-base font-semibold text-zinc-700 transition-colors hover:border-yellow-500 hover:text-yellow-700"
          >
            <Sparkles className="h-5 w-5 text-yellow-600" /> Explore the AI
          </Link>
        </div>

        <div className="mx-auto mt-14 grid max-w-3xl grid-cols-2 gap-3 md:grid-cols-4">
          <LiveStat label="Active Crises" value={data?.active_last_30d ?? null} loading={isLoading} emphasis />
          <LiveStat label="Countries Hit" value={data?.countries_impacted ?? null} loading={isLoading} />
          <LiveStat label="Critical (5/5)" value={data?.by_severity?.[5] ?? null} loading={isLoading} emphasis />
          <LiveStat label="Crisis Categories" value={Object.keys(data?.by_type ?? {}).length || null} loading={isLoading} />
        </div>
      </section>

      {/* Trust strip */}
      <section className="border-y border-zinc-200 bg-zinc-50">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-center gap-x-10 gap-y-3 px-6 py-5 text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
          <span className="text-yellow-600">Data from</span>
          <span>GDACS</span><span className="text-zinc-300">•</span>
          <span>USGS</span><span className="text-zinc-300">•</span>
          <span>NASA FIRMS</span><span className="text-zinc-300">•</span>
          <span>ReliefWeb</span><span className="text-zinc-300">•</span>
          <span>WHO</span><span className="text-zinc-300">•</span>
          <span>ACLED</span><span className="text-zinc-300">•</span>
          <span>Open-Meteo</span>
        </div>
      </section>

      {/* Pillars */}
      <section id="features" className="mx-auto max-w-7xl scroll-mt-20 px-6 py-20">
        <div className="mb-12 text-center">
          <div className="mb-3 text-xs font-bold uppercase tracking-[0.25em] text-yellow-600">The Platform</div>
          <h2 className="text-3xl font-extrabold text-zinc-900 md:text-5xl">Built like an ops center, powered by AI</h2>
          <p className="mx-auto mt-4 max-w-xl text-zinc-500">
            Four capabilities every humanitarian coordination cell needs — fused into one screen.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
          {pillars.map(({ icon: Icon, title, desc, color }) => (
            <div
              key={title}
              className="group relative overflow-hidden rounded-2xl border border-zinc-200 bg-white p-6 transition-colors hover:border-yellow-400"
            >
              <div
                className="absolute -right-10 -top-10 h-32 w-32 rounded-full opacity-0 blur-3xl transition-opacity group-hover:opacity-30"
                style={{ backgroundColor: color }}
              />
              <div
                className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl"
                style={{ backgroundColor: `${color}1f`, color }}
              >
                <Icon className="h-6 w-6" />
              </div>
              <h3 className="text-lg font-bold text-zinc-900">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-zinc-500">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Models */}
      <section id="models" className="scroll-mt-20 border-y border-zinc-200 bg-zinc-50 py-20">
        <div className="mx-auto max-w-7xl px-6">
          <div className="mb-12 text-center">
            <div className="mb-3 text-xs font-bold uppercase tracking-[0.25em] text-yellow-600">The Intelligence Layer</div>
            <h2 className="text-3xl font-extrabold text-zinc-900 md:text-5xl">Four models. One explainable answer.</h2>
          </div>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {models.map(({ icon: Icon, name, model, metric, desc, accent }) => (
              <div
                key={name}
                className="flex gap-5 rounded-2xl border border-zinc-200 bg-white p-6 transition-colors hover:border-yellow-400"
              >
                <div
                  className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl"
                  style={{ backgroundColor: `${accent}1f`, color: accent }}
                >
                  <Icon className="h-6 w-6" />
                </div>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-base font-bold text-zinc-900">{name}</h3>
                    <span
                      className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
                      style={{ backgroundColor: `${accent}22`, color: accent === GOLD ? "#a16207" : accent }}
                    >
                      {model}
                    </span>
                    <span className="rounded-full border border-zinc-300 px-2 py-0.5 font-mono text-[10px] text-zinc-500">
                      {metric}
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-zinc-500">{desc}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3 text-center">
            <div className="flex items-center gap-2 rounded-full border border-yellow-500/40 bg-yellow-50 px-5 py-2.5 text-sm text-zinc-600">
              <ShieldCheck className="h-4 w-4 text-yellow-600" />
              Every prediction ships with SHAP feature attribution + plain-language rationale
            </div>
            <div className="flex items-center gap-2 rounded-full border border-zinc-300 bg-white px-5 py-2.5 text-sm text-zinc-600">
              <Zap className="h-4 w-4 text-yellow-600" />
              Demo-ready: all models include graceful offline fallbacks
            </div>
          </div>
        </div>
      </section>

      {/* Alert layer */}
      <section id="alerts" className="mx-auto max-w-7xl scroll-mt-20 px-6 py-20">
        <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-2">
          <div>
            <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.25em] text-yellow-600">
              <AlertTriangle className="h-4 w-4" /> The Alert Layer
            </div>
            <h2 className="text-3xl font-extrabold leading-tight text-zinc-900 md:text-4xl">
              Alerts ranked the way a war room ranks them. Not a spam feed.
            </h2>
            <p className="mt-4 max-w-lg text-zinc-500">
              The moment an event crosses the severity threshold, an alert is generated with full
              context — geolocation, affected populations, displacement — and queued by urgency.
              Acknowledge, triage, act.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link href="/alerts" className="inline-flex items-center gap-2 rounded-xl bg-gold px-6 py-3 text-sm font-bold text-black transition-colors hover:bg-lemon">
                <BellRing className="h-4 w-4" /> Open Alert Feed
              </Link>
              <Link href="/reports" className="inline-flex items-center gap-2 rounded-xl border border-zinc-300 px-6 py-3 text-sm font-semibold text-zinc-700 transition-colors hover:border-yellow-500 hover:text-yellow-700">
                <FileText className="h-4 w-4" /> Generate a Report
              </Link>
            </div>
          </div>

          <div className="relative">
            <div className="overflow-hidden rounded-2xl border border-yellow-500/40 bg-white">
              <div className="flex items-center gap-2 border-b border-zinc-200 px-5 py-3">
                <span className="h-3 w-3 rounded-full bg-yellow-500" />
                <span className="rounded-full bg-yellow-100 px-3 py-0.5 text-[11px] font-bold text-yellow-700">
                  CATASTROPHIC · severity 5/5
                </span>
                <span className="ml-auto font-mono text-[11px] text-zinc-500">live feed</span>
              </div>
              <div className="space-y-3 p-5">
                {[
                  { t: "Northwest Syria", d: "Renewed escalation displaces tens of thousands at the Turkish border crossing", s: "CATASTROPHIC" },
                  { t: "Sindh, Pakistan", d: "Monsoon floods submerge low-lying districts, 5,000+ displaced", s: "CRITICAL" },
                  { t: "Yemen", d: "Cholera outbreak expands beyond containment zones", s: "CRITICAL" },
                  { t: "Tohoku, Japan", d: "M8.1 earthquake triggers tsunami advisories", s: "HIGH" },
                ].map((a) => (
                  <div key={a.t} className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 transition-colors hover:border-yellow-400">
                    <div className="flex items-center gap-2">
                      <Globe className="h-3.5 w-3.5 text-zinc-400" />
                      <span className="text-sm font-semibold text-zinc-900">{a.t}</span>
                      <span className="ml-auto rounded-full bg-yellow-100 px-2 py-0.5 text-[10px] font-bold text-yellow-700">
                        {a.s}
                      </span>
                    </div>
                    <p className="mt-1.5 line-clamp-1 text-xs text-zinc-500">{a.d}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Open access */}
      <section id="open" className="scroll-mt-20 border-t border-zinc-200 bg-zinc-50 py-20">
        <div className="mx-auto max-w-7xl px-6 text-center">
          <div className="mb-3 text-xs font-bold uppercase tracking-[0.25em] text-yellow-600">Built in the open</div>
          <h2 className="mx-auto max-w-2xl text-3xl font-extrabold text-zinc-900 md:text-5xl">
            Critical infrastructure should never be a mystery.
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-zinc-500">
            Free public data in. Explainable intelligence out. Everything in this project is open
            source, MIT-licensed, and runs on a single machine — or at planetary scale.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
            <Link href="/dashboard" className="inline-flex items-center gap-2 rounded-2xl bg-gold px-8 py-4 text-base font-bold text-black transition-colors hover:bg-lemon">
              Start Exploring <ArrowRight className="h-5 w-5" />
            </Link>
            <a
              href="https://github.com/opeblow/CrisisWatchAI"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-2xl border border-zinc-300 px-8 py-4 text-base font-semibold text-zinc-700 transition-colors hover:border-yellow-500 hover:text-yellow-700"
            >
              <Globe className="h-5 w-5" /> View the Code
            </a>
          </div>
        </div>
      </section>

      <footer className="border-t border-zinc-200 py-8">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 text-xs text-zinc-500">
          <span>© 2026 CrisisWatch AI · MIT Licensed · Built for hackathon demo</span>
          <span className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-yellow-500 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-yellow-500" />
            </span>
            All systems operational
          </span>
        </div>
      </footer>
    </div>
  );
}