/**
 * Data Feeds API client — connects to Phase 2 AI Data Intelligence Layer.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

export interface GeoRiskData {
  geo_risk_score: number;
  gdelt_tone: string;
  gdelt_event_count: number;
  earthquake_count: number;
  max_earthquake_magnitude: string;
  summary: string;
  updated_at: string | null;
}

export interface NewsFeedData {
  summary: string;
  sentiment: "positive" | "neutral" | "negative";
  key_events: string[];
  sources_count: number;
  updated_at: string | null;
}

export interface FinanceFeedData {
  macro_summary: string;
  fed_stance: "hawkish" | "neutral" | "dovish" | "unknown";
  stablecoin_risk: "low" | "medium" | "high";
  key_indicators: string[];
  sources_count: number;
  updated_at: string | null;
}

export interface AgentSignal {
  agent_name: string;
  bias: "bullish" | "neutral" | "bearish";
  confidence: number;
  reasoning: string;
  key_data: Record<string, unknown>;
}

export interface AgentsData {
  consensus: "bullish" | "neutral" | "bearish";
  average_confidence: number;
  agents: {
    indicator: AgentSignal | null;
    pattern: AgentSignal | null;
    risk: AgentSignal | null;
    macro: AgentSignal | null;
  };
  decision_prompt_preview: string;
}

export async function fetchGeoRisk(token: string): Promise<GeoRiskData> {
  const res = await fetch(`${API_BASE}/api/data-feeds/geo-risk`, { headers: authHeaders(token) });
  if (!res.ok) throw new Error(`geo-risk: ${res.status}`);
  return res.json();
}

export async function fetchNews(token: string): Promise<NewsFeedData> {
  const res = await fetch(`${API_BASE}/api/data-feeds/news`, { headers: authHeaders(token) });
  if (!res.ok) throw new Error(`news: ${res.status}`);
  return res.json();
}

export async function fetchFinance(token: string): Promise<FinanceFeedData> {
  const res = await fetch(`${API_BASE}/api/data-feeds/finance`, { headers: authHeaders(token) });
  if (!res.ok) throw new Error(`finance: ${res.status}`);
  return res.json();
}

export async function fetchAgents(token: string): Promise<AgentsData> {
  const res = await fetch(`${API_BASE}/api/data-feeds/agents`, { headers: authHeaders(token) });
  if (!res.ok) throw new Error(`agents: ${res.status}`);
  return res.json();
}

export async function refreshGeoRisk(token: string): Promise<GeoRiskData> {
  const res = await fetch(`${API_BASE}/api/data-feeds/geo-risk/refresh`, { method: "POST", headers: authHeaders(token) });
  if (!res.ok) throw new Error(`geo-risk refresh: ${res.status}`);
  return res.json();
}

export async function refreshNews(token: string): Promise<NewsFeedData> {
  const res = await fetch(`${API_BASE}/api/data-feeds/news/refresh`, { method: "POST", headers: authHeaders(token) });
  if (!res.ok) throw new Error(`news refresh: ${res.status}`);
  return res.json();
}

export async function refreshFinance(token: string): Promise<FinanceFeedData> {
  const res = await fetch(`${API_BASE}/api/data-feeds/finance/refresh`, { method: "POST", headers: authHeaders(token) });
  if (!res.ok) throw new Error(`finance refresh: ${res.status}`);
  return res.json();
}
