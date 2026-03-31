// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client";

import { useEffect, useState, useCallback } from "react";
import {
  fetchGeoRisk,
  fetchNews,
  fetchFinance,
  fetchAgents,
  refreshGeoRisk,
  refreshNews,
  refreshFinance,
  GeoRiskData,
  NewsFeedData,
  FinanceFeedData,
  AgentsData,
} from "@/lib/api/data-feeds";

/* ───── helpers ───── */
function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("ultra_auth_token") ?? "";
}

function timeAgo(iso: string | null): string {
  if (!iso) return "unknown";
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  return `${Math.floor(min / 60)}h ${min % 60}m ago`;
}

function biasColor(bias: string) {
  if (bias === "bullish") return "text-emerald-400";
  if (bias === "bearish") return "text-red-400";
  return "text-yellow-400";
}

function biasEmoji(bias: string) {
  if (bias === "bullish") return "🟢";
  if (bias === "bearish") return "🔴";
  return "🟡";
}

function riskColor(score: number) {
  if (score >= 70) return "text-red-400";
  if (score >= 40) return "text-yellow-400";
  return "text-emerald-400";
}

function sentimentColor(s: string) {
  if (s === "positive") return "text-emerald-400";
  if (s === "negative") return "text-red-400";
  return "text-yellow-400";
}

function fedColor(f: string) {
  if (f === "dovish") return "text-emerald-400";
  if (f === "hawkish") return "text-red-400";
  return "text-yellow-400";
}

function stablecoinColor(r: string) {
  if (r === "high") return "text-red-400";
  if (r === "medium") return "text-yellow-400";
  return "text-emerald-400";
}

/* ───── card components ───── */
function Card({ title, children, updatedAt, onRefresh, refreshing }: {
  title: string;
  children: React.ReactNode;
  updatedAt?: string | null;
  onRefresh?: () => void;
  refreshing?: boolean;
}) {
  return (
    <div className="rounded-xl border border-zinc-700 bg-zinc-900/60 p-5 backdrop-blur">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wide">{title}</h3>
        <div className="flex items-center gap-2">
          {updatedAt && <span className="text-xs text-zinc-500">{timeAgo(updatedAt)}</span>}
          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={refreshing}
              className="text-xs px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400 disabled:opacity-50"
            >
              {refreshing ? "..." : "↻"}
            </button>
          )}
        </div>
      </div>
      {children}
    </div>
  );
}

type AgentSignal = NonNullable<AgentsData["agents"]["indicator"]>;

function AgentCard({ signal }: { signal: AgentSignal | null }) {
  if (!signal) return <div className="text-zinc-600 text-sm">No data</div>;
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <span>{biasEmoji(signal.bias)}</span>
        <span className={`font-bold text-sm ${biasColor(signal.bias)}`}>{signal.bias.toUpperCase()}</span>
        <span className="text-xs text-zinc-500">({signal.confidence}%)</span>
      </div>
      <p className="text-xs text-zinc-400 leading-relaxed">{signal.reasoning}</p>
    </div>
  );
}

/* ───── main page ───── */
export default function DataFeedsPage() {
  const [geo, setGeo] = useState<GeoRiskData | null>(null);
  const [news, setNews] = useState<NewsFeedData | null>(null);
  const [finance, setFinance] = useState<FinanceFeedData | null>(null);
  const [agents, setAgents] = useState<AgentsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState<Record<string, boolean>>({});

  const loadAll = useCallback(async () => {
    const token = getToken();
    if (!token) { setError("Not authenticated"); return; }
    try {
      const [g, n, f, a] = await Promise.all([
        fetchGeoRisk(token), fetchNews(token), fetchFinance(token), fetchAgents(token),
      ]);
      setGeo(g); setNews(n); setFinance(f); setAgents(a);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    loadAll();
    const id = setInterval(loadAll, 60000);
    return () => clearInterval(id);
  }, [loadAll]);

  const doRefresh = async (key: string, fn: (t: string) => Promise<unknown>) => {
    setRefreshing(r => ({ ...r, [key]: true }));
    try { await fn(getToken()); await loadAll(); } catch { /* ignore */ }
    setRefreshing(r => ({ ...r, [key]: false }));
  };

  if (error) return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
      <div className="text-red-400 bg-red-950/30 border border-red-800 rounded-lg p-6">
        <p className="font-bold">Error</p><p className="text-sm mt-1">{error}</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">AI Data Intelligence</h1>
            <p className="text-sm text-zinc-500 mt-1">Phase 2 — Real-time market context for AI judgment</p>
          </div>
          {agents && (
            <div className="text-right">
              <div className={`text-3xl font-bold ${biasColor(agents.consensus)}`}>
                {biasEmoji(agents.consensus)} {agents.consensus.toUpperCase()}
              </div>
              <div className="text-xs text-zinc-500">Consensus • {agents.average_confidence}% confidence</div>
            </div>
          )}
        </div>

        {/* Top row: 4 agent cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {(["indicator", "pattern", "risk", "macro"] as const).map(key => (
            <Card key={key} title={agents?.agents[key]?.agent_name?.split("(")[0]?.trim() ?? key}>
              <AgentCard signal={agents?.agents[key] ?? null} />
            </Card>
          ))}
        </div>

        {/* Second row: Geo Risk + News */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card title="Geopolitical Risk" updatedAt={geo?.updated_at}
            onRefresh={() => doRefresh("geo", refreshGeoRisk)} refreshing={refreshing.geo}>
            {geo ? (
              <div className="space-y-3">
                <div className="flex items-baseline gap-3">
                  <span className={`text-4xl font-bold ${riskColor(geo.geo_risk_score)}`}>{geo.geo_risk_score}</span>
                  <span className="text-zinc-500 text-sm">/ 100</span>
                </div>
                <p className="text-sm text-zinc-400">{geo.summary}</p>
                <div className="flex gap-4 text-xs text-zinc-500">
                  <span>Events: {geo.gdelt_event_count}</span>
                  <span>Quakes: {geo.earthquake_count}</span>
                  {Number(geo.max_earthquake_magnitude) > 0 && <span>Max M{geo.max_earthquake_magnitude}</span>}
                </div>
              </div>
            ) : <div className="animate-pulse h-20 bg-zinc-800 rounded" />}
          </Card>

          <Card title="Crypto / DeFi News" updatedAt={news?.updated_at}
            onRefresh={() => doRefresh("news", refreshNews)} refreshing={refreshing.news}>
            {news ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs uppercase font-bold px-2 py-0.5 rounded bg-zinc-800">Sentiment</span>
                  <span className={`font-bold text-sm ${sentimentColor(news.sentiment)}`}>{news.sentiment}</span>
                  <span className="text-xs text-zinc-500">({news.sources_count} sources)</span>
                </div>
                <p className="text-sm text-zinc-400 leading-relaxed">{news.summary}</p>
                {news.key_events.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-xs text-zinc-500 font-semibold">Key Events:</span>
                    {news.key_events.map((e, i) => (
                      <p key={i} className="text-xs text-zinc-500 pl-3">• {e}</p>
                    ))}
                  </div>
                )}
              </div>
            ) : <div className="animate-pulse h-32 bg-zinc-800 rounded" />}
          </Card>
        </div>

        {/* Third row: Finance / Macro */}
        <Card title="Macro Economy" updatedAt={finance?.updated_at}
          onRefresh={() => doRefresh("finance", refreshFinance)} refreshing={refreshing.finance}>
          {finance ? (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-4">
                <div className="flex items-center gap-2">
                  <span className="text-xs uppercase font-bold px-2 py-0.5 rounded bg-zinc-800">FED</span>
                  <span className={`font-bold text-sm ${fedColor(finance.fed_stance)}`}>{finance.fed_stance}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs uppercase font-bold px-2 py-0.5 rounded bg-zinc-800">Stablecoin Risk</span>
                  <span className={`font-bold text-sm ${stablecoinColor(finance.stablecoin_risk)}`}>{finance.stablecoin_risk}</span>
                </div>
                <span className="text-xs text-zinc-500">({finance.sources_count} sources)</span>
              </div>
              <p className="text-sm text-zinc-400 leading-relaxed">{finance.macro_summary}</p>
              {finance.key_indicators.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {finance.key_indicators.map((ind, i) => (
                    <span key={i} className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-400">{ind}</span>
                  ))}
                </div>
              )}
            </div>
          ) : <div className="animate-pulse h-24 bg-zinc-800 rounded" />}
        </Card>
      </div>
    </div>
  );
}
