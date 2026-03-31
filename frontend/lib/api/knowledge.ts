// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/knowledge.ts
import { getJson, postJson } from "./http";
import { getStoredToken } from "../auth";

export type KnowledgeItemStatus = "pending" | "analyzed" | "skipped" | "error";
export type KnowledgeItemType = "url" | "text";

export interface KnowledgeItem {
  id: number;
  source_url: string | null;
  title: string | null;
  raw_text: string | null;
  status: KnowledgeItemStatus;
  chunk_count: number;
  item_type: KnowledgeItemType;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeCreateRequest {
  title?: string;
  item_type: KnowledgeItemType;
  source_url?: string;
  raw_text?: string;
}

export interface KnowledgeSearchRequest {
  query: string;
  top_k?: number;
}

export interface KnowledgeSearchResult {
  chunk_id: number;
  document_id: number;
  content: string;
  similarity: number;
  source_url: string | null;
  title: string | null;
}

export interface KnowledgeSearchResponse {
  results: KnowledgeSearchResult[];
  count: number;
  query: string;
}

function authHeaders(): HeadersInit {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function fetchKnowledgeItems(status?: string): Promise<KnowledgeItem[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return getJson<KnowledgeItem[]>(`/knowledge/items${q}`, {
    headers: authHeaders(),
  });
}

export async function createKnowledgeItem(req: KnowledgeCreateRequest): Promise<KnowledgeItem> {
  return postJson<KnowledgeItem>("/knowledge/items", req, {
    headers: authHeaders(),
  });
}

export async function searchKnowledge(req: KnowledgeSearchRequest): Promise<KnowledgeSearchResponse> {
  return postJson<KnowledgeSearchResponse>("/knowledge/search", req, {
    headers: authHeaders(),
  });
}
