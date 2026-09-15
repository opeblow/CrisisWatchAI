"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BellRing,
  BrainCircuit,
  FileText,
  Gauge,
  Globe,
  LineChart,
  MapPin,
  Radar,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import { getStats } from "@/lib/api";
import { formatNumber } from "@/lib/utils";

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55 } },
};

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.09 } },
};

function LiveStat({
  label,
  value,
  loading,
  color,
}: {
  label: string;
  value: number | null;
  loading: boolean;
  color: string;
}) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-white/10 bg-white/[0.04] px-6 py-5 backdrop-blur-xl">
      <div
        className="text-3xl font-extrabold tracking-tight md:text-4xl"
        style={{ color }}
      >
        {loading ? "—" : value != null ? formatNumber(value) : "—"}
      </div>
      <div className="mt-1 text-xs font-medium uppercase tracking-widest text-slate-500">
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
      title: "Always Watching",
      desc: "CrisisWatch ingests earthquakes, cyclones, floods, wildfires, droughts, epidemics, displacement and conflict from 7+ public real-time feeds, 24/7.",
      color: "#22d3ee",
    },
    {
      icon: BrainCircuit,
      title: "Think Like an Analyst",
      desc: "Four ML models interpret the noise — XGBoost rates severity, DistilBERT reads situation reports, Prophet predicts what's coming and HDBSCAN finds where it clusters.",
      color: "#a855f7",
    },
    {
      icon: ShieldCheck,
      title: "Explain Every Decision",
      desc: "AI you can audit. Every prediction shows its top contributing features in plain language — so a decision-maker never takes a black box at face value.",
      color: "#22c55e",
    },
    {
      icon: BellRing,
      title: "Arrest Attention",
      desc: "Priority-ranked alerts hit the moment an event crosses the severity threshold — ranked the way an ops center would rank them, not a spam feed.",
      color: "#ef4444",
    },
  ];

  const models = [
    {
      name: "Severity Classifier",
      model: "XGBoost",
      metric: "97.7% confidence",
      desc: "Rates any in-progress event on a unified 1–5 risk scale using 7+ contextual features, backed by SHAP attribution.",
      icon: Gauge,
      color: "#3b82f6",
    },
    {
      name: "Situation Report NLP",
      model: "DistilBERT",
      metric: "8 categories",
      desc: "Classifies incoming text reports into crisis types instantly — auto-tagging field notes and news wire copy.",
      icon: FileText,
      color: "#22d3ee",
    },
    {
      name: "Regional Forecaster",
      model: "Prophet",
      metric: "95% intervals",
      desc: "Panels next weeks of crisis frequency per region with confidence bands, so logistics can preposition resources.",
      icon: LineChart,
      color: "#f59e0b",
    },
    {
      name: "Hotspot Clustering",
      model: "HDBSCAN",
      metric: "risk-scored",
      desc: "Spots emerging crisis zones by density and severity — the difference between reacting and getting there first.",
      icon: Radar,
      color: "#a855f7",
    },
  ];

  return (
    <div className="relative min-h-screen overflow-x-clip">
      {/* Nav */}
      <header className="sticky top-0 z-40 border-b border-white/5 bg-navy-deep/70 backdrop-blur-2xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 shadow-lg shadow-blue-500/30">
              <Activity className="h-6 w-6 text-white" />
            </div>
            <div>
              <div className="text-base font-extrabold tracking-tight text-white">
                CrisisWatch <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">AI</span>
              </div>
              <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-slate-500">
                Global Intelligence
              </div>
            </div>
          </div>
          <nav className="hidden items-center gap-6 text-sm font-medium text-slate-300 md:flex">
            <a href="#features" className="transition-colors hover:text-white">Features</a>
            <a href="#models" className="transition-colors hover:text-white">Intelligence</a>
            <a href="#sources" className="transition-colors hover:text-white">Sources</a>
            <a href="#open" className="transition-colors hover:text-white">Open Access</a>
          </nav>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-xl bg-blue-500 px-5 py-2.5 text-sm font-bold text-white shadow-lg shadow-blue-500/30 transition-all hover:bg-blue-400"
          >
            Open Dashboard <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="relative mx-auto max-w-7xl px-6 pt-20 pb-16 text-center md:pt-28">
        <div className="pointer-events-none absolute inset-0 -z-10">
          <div className="absolute left-1/2 top-0 h-[500px] w-[900px] -translate-x-1/2 rounded-full bg-blue-600/10 blur-[120px]" />
          <div className="absolute right-0 top-40 h-72 w-72 rounded-full bg-purple-600/10 blur-[100px]" />
        </div>

        <motion.div variants={stagger} initial="hidden" animate="show">
          <motion.div
            variants={fadeUp}
            className="mb-6 inline-flex items-center gap-2 rounded-full border border-blue-400/25 bg-blue-500/10 px-4 py-1.5 text-xs font-semibold text-blue-300"
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-blue-400" />
            </span>
            Live · tracking {data?.total_events ? formatNumber(data.total_events) : "—"} events across{" "}
            {data?.countries_impacted ? formatNumber(data.countries_impacted) : "—"} countries
          </motion.div>

          <motion.h1
            variants={fadeUp}
            className="mx-auto max-w-4xl text-5xl font-extrabold leading-[1.05] tracking-tight text-white md:text-7xl"
          >
            Turn scattered crisis data into{" "}
            <span className="bg-gradient-to-r from-blue-400 via-cyan-300 to-purple-400 bg-clip-text text-transparent">
              life-saving action
            </span>
          </motion.h1>

          <motion.p
            variants={fadeUp}
            className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-slate-400"
          >
            One explainable intelligence layer on top of every disaster feed on Earth. COVID
            outbreaks, floods, earthquakes, conflict — aggregated, scored, forecast and delivered
            before it&apos;s too late.
          </motion.p>

          <motion.div variants={fadeUp} className="mt-9 flex flex-wrap items-center justify-center gap-4">
            <Link
              href="/dashboard"
              className="group inline-flex items-center gap-2 rounded-2xl bg-gradient-to-r from-blue-500 to-blue-600 px-8 py-4 text-base font-bold text-white shadow-xl shadow-blue-500/30 transition-all hover:shadow-blue-400/40"
            >
              Enter the Dashboard
              <ArrowRight className="h-5 w-5 transition-transform group-hover:translate-x-1" />
            </Link>
            <Link
              href="/predictions"
              className="inline-flex items-center gap-2 rounded-2xl border border-white/15 px-8 py-4 text-base font-semibold text-slate-200 transition-colors hover:bg-white/10"
            >
              <Sparkles className="h-5 w-5 text-purple-400" /> Explore the AI
            </Link>
          </motion.div>

          <motion.div variants={fadeUp} className="mx-auto mt-14 grid max-w-3xl grid-cols-2 gap-3 md:grid-cols-4">
            <LiveStat label="Active Crises" value={data?.active_last_30d ?? null} loading={isLoading} color="#60a5fa" />
            <LiveStat label="Countries Hit" value={data?.countries_impacted ?? null} loading={isLoading} color="#34d399" />
            <LiveStat label="Critical (5/5)" value={data?.by_severity?.[5] ?? null} loading={isLoading} color="#f87171" />
            <LiveStat label="Crisis Categories" value={Object.keys(data?.by_type ?? {}).length || null} loading={isLoading} color="#c084fc" />
          </motion.div>
        </motion.div>
      </section>

      {/* Trust strip */}
      <section className="border-y border-white/5 bg-white/[0.02]">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-center gap-x-10 gap-y-3 px-6 py-5 text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
          <span className="text-slate-400">Data from</span>
          <span>GDACS</span><span className="text-slate-700">•</span>
          <span>USGS</span><span className="text-slate-700">•</span>
          <span>NASA FIRMS</span><span className="text-slate-700">•</span>
          <span>ReliefWeb</span><span className="text-slate-700">•</span>
          <span>WHO</span><span className="text-slate-700">•</span>
          <span>ACLED</span><span className="text-slate-700">•</span>
          <span>Open-Meteo</span>
        </div>
      </section>

      {/* Pillars */}
      <section id="features" className="mx-auto max-w-7xl px-6 py-20">
        <motion.div variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true }} className="mb-12 text-center">
          <div className="mb-3 text-xs font-bold uppercase tracking-[0.25em] text-blue-400">The Platform</div>
          <h2 className="text-3xl font-extrabold text-white md:text-5xl">Built like an ops center, powered by AI</h2>
          <p className="mx-auto mt-4 max-w-xl text-slate-400">
            Four capabilities every humanitarian coordination cell needs — fused into one screen.
          </p>
        </motion.div>

        <motion.div variants={stagger} initial="hidden" whileInView="show" viewport={{ once: true }} className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
          {pillars.map(({ icon: Icon, title, desc, color }) => (
            <motion.div
              key={title}
              variants={fadeUp}
              className="group relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-xl transition-colors hover:border-white/25"
            >
              <div
                className="absolute -right-10 -top-10 h-32 w-32 rounded-full opacity-0 blur-3xl transition-opacity group-hover:opacity-30"
                style={{ backgroundColor: color }}
              />
              <div
                className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl"
                style={{ backgroundColor: `${color}1a`, color }}
              >
                <Icon className="h-6 w-6" />
              </div>
              <h3 className="text-lg font-bold text-white">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">{desc}</p>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* Models */}
      <section id="models" className="relative border-y border-white/5 bg-white/[0.02] py-20">
        <div className="mx-auto max-w-7xl px-6">
          <motion.div variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true }} className="mb-12 text-center">
            <div className="mb-3 text-xs font-bold uppercase tracking-[0.25em] text-purple-400">The Intelligence Layer</div>
            <h2 className="text-3xl font-extrabold text-white md:text-5xl">Four models. One explainable answer.</h2>
          </motion.div>

          <motion.div variants={stagger} initial="hidden" whileInView="show" viewport={{ once: true }} className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {models.map(({ icon: Icon, name, model, metric, desc, color }) => (
              <motion.div
                key={name}
                variants={fadeUp}
                className="flex gap-5 rounded-2xl border border-white/10 bg-navy-deep/60 p-6 backdrop-blur-xl transition-colors hover:border-white/25"
              >
                <div
                  className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl"
                  style={{ backgroundColor: `${color}1a`, color }}
                >
                  <Icon className="h-6 w-6" />
                </div>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-base font-bold text-white">{name}</h3>
                    <span
                      className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
                      style={{ backgroundColor: `${color}22`, color }}
                    >
                      {model}
                    </span>
                    <span className="rounded-full border border-white/15 px-2 py-0.5 font-mono text-[10px] text-slate-400">
                      {metric}
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-slate-400">{desc}</p>
                </div>
              </motion.div>
            ))}
          </motion.div>

          <motion.div variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true }} className="mt-10 flex flex-wrap items-center justify-center gap-3 text-center">
            <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-5 py-2.5 text-sm text-slate-300">
              <ShieldCheck className="h-4 w-4 text-green-400" />
              Every prediction ships with SHAP feature attribution + plain-language rationale
            </div>
            <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-5 py-2.5 text-sm text-slate-300">
              <TrendingUp className="h-4 w-4 text-blue-400" />
              Demo-ready: all models include graceful offline fallbacks
            </div>
          </motion.div>
        </div>
      </section>

      {/* Live feed teaser */}
      <section className="mx-auto max-w-7xl px-6 py-20">
        <motion.div variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true }} className="grid grid-cols-1 items-center gap-10 lg:grid-cols-2">
          <div>
            <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.25em] text-red-400">
              <AlertTriangle className="h-4 w-4" /> The Alert Layer
            </div>
            <h2 className="text-3xl font-extrabold leading-tight text-white md:text-4xl">
              Alerts ranked the way a war room ranks them. Not a spam feed.
            </h2>
            <p className="mt-4 max-w-lg text-slate-400">
              The moment an event crosses the severity threshold, an alert is generated with full
              context — geolocation, affected populations, displacement — and queued by urgency.
              Acknowledge, triage, act.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link href="/alerts" className="inline-flex items-center gap-2 rounded-xl bg-red-500/90 px-6 py-3 text-sm font-bold text-white shadow-lg shadow-red-500/25 transition-colors hover:bg-red-400">
                <BellRing className="h-4 w-4" /> Open Alert Feed
              </Link>
              <Link href="/reports" className="inline-flex items-center gap-2 rounded-xl border border-white/15 px-6 py-3 text-sm font-semibold text-slate-200 transition-colors hover:bg-white/10">
                <FileText className="h-4 w-4" /> Generate a Report
              </Link>
            </div>
          </div>

          <motion.div
            variants={fadeUp}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true }}
            className="relative"
          >
            <div className="absolute -inset-4 -z-10 rounded-3xl bg-gradient-to-br from-blue-600/10 to-purple-600/10 blur-2xl" />
            <div className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] backdrop-blur-xl">
              <div className="flex items-center gap-2 border-b border-white/10 px-5 py-3">
                <span className="h-3 w-3 rounded-full bg-red-400" />
                <span className="rounded-full bg-red-400/15 px-3 py-0.5 text-[11px] font-bold text-red-300">
                  CATASTROPHIC · severity 5/5
                </span>
                <span className="ml-auto font-mono text-[11px] text-slate-500">live feed</span>
              </div>
              <div className="space-y-3 p-5">
                {[
                  { t: "Northwest Syria", d: "Renewed escalation displaces tens of thousands at the Turkish border crossing", s: "CATASTROPHIC", c: "#ef4444" },
                  { t: "Sindh, Pakistan", d: "Monsoon floods submerge low-lying districts, 5,000+ displaced", s: "SEVERE", c: "#f59e0b" },
                  { t: "Yemen", d: "Cholera outbreak expands beyond containment zones", s: "SEVERE", c: "#f59e0b" },
                  { t: "Tohoku, Japan", d: "M8.1 earthquake triggers tsunami advisories", s: "HIGH", c: "#3b82f6" },
                ].map((a) => (
                  <div key={a.t} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                    <div className="flex items-center gap-2">
                      <MapPin className="h-3.5 w-3.5 text-slate-500" />
                      <span className="text-sm font-semibold text-white">{a.t}</span>
                      <span
                        className="ml-auto rounded-full px-2 py-0.5 text-[10px] font-bold"
                        style={{ backgroundColor: `${a.c}22`, color: a.c }}
                      >
                        {a.s}
                      </span>
                    </div>
                    <p className="mt-1.5 line-clamp-1 text-xs text-slate-400">{a.d}</p>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        </motion.div>
      </section>

      {/* Open access */}
      <section id="open" className="border-t border-white/5 bg-white/[0.02] py-20">
        <div className="mx-auto max-w-7xl px-6 text-center">
          <motion.div variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true }}>
            <div className="mb-3 text-xs font-bold uppercase tracking-[0.25em] text-blue-400">Built in the open</div>
            <h2 className="mx-auto max-w-2xl text-3xl font-extrabold text-white md:text-5xl">
              Critical infrastructure should never be a mystery.
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-slate-400">
              Free public data in. Explainable intelligence out. Everything in this project is open
              source, MIT-licensed, and runs on a single machine — or at planetary scale.
            </p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
              <Link href="/dashboard" className="inline-flex items-center gap-2 rounded-2xl bg-gradient-to-r from-blue-500 to-blue-600 px-8 py-4 text-base font-bold text-white shadow-xl shadow-blue-500/30">
                Start Exploring <ArrowRight className="h-5 w-5" />
              </Link>
              <a
                href="https://github.com"
                className="inline-flex items-center gap-2 rounded-2xl border border-white/15 px-8 py-4 text-base font-semibold text-slate-200 transition-colors hover:bg-white/10"
              >
                <Globe className="h-5 w-5" /> View the Code
              </a>
            </div>
          </motion.div>
        </div>
      </section>

      <footer className="border-t border-white/5 py-8">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 text-xs text-slate-600">
          <span>© 2026 CrisisWatch AI · MIT Licensed · Built for hackathon demo</span>
          <span className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-green-400" />
            </span>
            All systems operational
          </span>
        </div>
      </footer>
    </div>
  );
}