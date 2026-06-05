// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
export type HttpError = {
  status: number;
  message: string;
  detail?: unknown;
};

/**
 * Resolution order:
 * 1) If NEXT_PUBLIC_API_URL is set, call backend directly from the browser.
 *    (This may require CORS on the backend.)
 * 2) Otherwise call same-origin (/api/...) which is proxied by Next.js API routes to BACKEND_BASE_URL.
 */
function getBaseUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_URL;
  if (!base) return "";
  return base.replace(/\/$/, "");
}

// MOCK_MODE: path prefix → mock JSON file mapping
const MOCK_PATH_MAP: Array<[string | RegExp, string]> = [
  ["/api/proposals/admin/stats", "/mock/proposal_stats.json"],
  ["/api/proposals/admin/all", "/mock/proposals.json"],
  ["/api/proposals", "/mock/proposals.json"],
  ["/api/partner/performance", "/mock/performance.json"],
  ["/api/partner/allocations", "/mock/fund_allocations.json"],
  ["/api/admin/transactions", "/mock/transactions.json"],
  ["/api/ai/decisions", "/mock/ai_decisions.json"],
  ["/api/admin/users", "/mock/users.json"],
  ["/api/users", "/mock/users.json"],
  ["/api/aave", "/mock/aave_positions.json"],
  ["/health", "/mock/stats.json"],
  ["/api/health", "/mock/stats.json"],
];

function getMockFile(path: string): string | null {
  for (const [pattern, file] of MOCK_PATH_MAP) {
    if (typeof pattern === "string" ? path.startsWith(pattern) : pattern.test(path)) {
      return file;
    }
  }
  return null;
}

async function mockFetch<T>(path: string): Promise<T> {
  const mockFile = getMockFile(path);
  if (!mockFile) {
    // Return empty/null for unmapped paths in mock mode
    return null as T;
  }
  const res = await fetch(mockFile, { cache: "no-store" });
  if (!res.ok) throw { status: res.status, message: `Mock file not found: ${mockFile}` } as HttpError;
  return res.json() as Promise<T>;
}

function isMockMode(): boolean {
  return process.env.NEXT_PUBLIC_MOCK_MODE === "true";
}

export async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  if (isMockMode()) return mockFetch<T>(path);
  const base = getBaseUrl();
  const url = base ? `${base}${path}` : path;

  const res = await fetch(url, {
    credentials: "include",
    ...init,
    method: "GET",
    headers: { "Accept": "application/json", ...init?.headers },
  });

  const text = await res.text();
  const body = text ? safeJsonParse(text) : undefined;

  if (!res.ok) {
    const msg =
      typeof body === "object" && body && "detail" in (body as any)
        ? extractDetail((body as any).detail)
        : `HTTP ${res.status}`;
    throw { status: res.status, message: msg, detail: body } as HttpError;
  }
  return body as T;
}

export async function postJson<T>(
  path: string,
  data: unknown,
  init?: RequestInit
): Promise<T> {
  if (isMockMode()) return mockFetch<T>(path);
  const base = getBaseUrl();
  const url = base ? `${base}${path}` : path;

  const res = await fetch(url, {
    credentials: "include",
    ...init,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
      ...init?.headers,
    },
    body: JSON.stringify(data),
  });

  const text = await res.text();
  const body = text ? safeJsonParse(text) : undefined;

  if (!res.ok) {
    const msg =
      typeof body === "object" && body && "detail" in (body as any)
        ? extractDetail((body as any).detail)
        : `HTTP ${res.status}`;
    throw { status: res.status, message: msg, detail: body } as HttpError;
  }
  return body as T;
}

export async function putJson<T>(
  path: string,
  data: unknown,
  init?: RequestInit
): Promise<T> {
  if (isMockMode()) return mockFetch<T>(path);
  const base = getBaseUrl();
  const url = base ? `${base}${path}` : path;

  const res = await fetch(url, {
    credentials: "include",
    ...init,
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
      ...init?.headers,
    },
    body: JSON.stringify(data),
  });

  const text = await res.text();
  const body = text ? safeJsonParse(text) : undefined;

  if (!res.ok) {
    const msg =
      typeof body === "object" && body && "detail" in (body as any)
        ? extractDetail((body as any).detail)
        : `HTTP ${res.status}`;
    throw { status: res.status, message: msg, detail: body } as HttpError;
  }
  return body as T;
}

export async function deleteJson<T>(path: string, init?: RequestInit): Promise<T> {
  if (isMockMode()) return mockFetch<T>(path);
  const base = getBaseUrl();
  const url = base ? `${base}${path}` : path;

  const res = await fetch(url, {
    credentials: "include",
    ...init,
    method: "DELETE",
    headers: { "Accept": "application/json", ...init?.headers },
  });

  const text = await res.text();
  const body = text ? safeJsonParse(text) : undefined;

  if (!res.ok) {
    const msg =
      typeof body === "object" && body && "detail" in (body as any)
        ? extractDetail((body as any).detail)
        : `HTTP ${res.status}`;
    throw { status: res.status, message: msg, detail: body } as HttpError;
  }
  return body as T;
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

// FastAPI 422 の detail は配列 [{loc, msg, type}] になる。
// String(array) は "[object Object]" になるので msg を抽出して結合する。
function extractDetail(detail: unknown): string {
  if (Array.isArray(detail)) {
    return detail
      .map((e: unknown) =>
        e && typeof e === "object" && "msg" in e ? String((e as { msg: unknown }).msg) : String(e)
      )
      .join(", ");
  }
  return String(detail);
}
