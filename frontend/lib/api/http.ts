// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
export type HttpError = {
  status: number;
  message: string;
  detail?: unknown;
};

/**
 * Resolution order:
 * 1) If NEXT_PUBLIC_BACKEND_BASE_URL is set, call backend directly from the browser.
 *    (This may require CORS on the backend.)
 * 2) Otherwise call same-origin (/api/...) which is proxied by Next.js API routes to BACKEND_BASE_URL.
 */
function getBaseUrl(): string {
  const base = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;
  if (!base) return "";
  return base.replace(/\/$/, "");
}

export async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getBaseUrl();
  const url = base ? `${base}${path}` : path;

  const res = await fetch(url, {
    ...init,
    method: "GET",
    headers: { "Accept": "application/json", ...init?.headers },
  });

  const text = await res.text();
  const body = text ? safeJsonParse(text) : undefined;

  if (!res.ok) {
    const msg =
      typeof body === "object" && body && "detail" in (body as any)
        ? String((body as any).detail)
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
  const base = getBaseUrl();
  const url = base ? `${base}${path}` : path;

  const res = await fetch(url, {
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
        ? String((body as any).detail)
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
  const base = getBaseUrl();
  const url = base ? `${base}${path}` : path;

  const res = await fetch(url, {
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
        ? String((body as any).detail)
        : `HTTP ${res.status}`;
    throw { status: res.status, message: msg, detail: body } as HttpError;
  }
  return body as T;
}

export async function deleteJson<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getBaseUrl();
  const url = base ? `${base}${path}` : path;

  const res = await fetch(url, {
    ...init,
    method: "DELETE",
    headers: { "Accept": "application/json", ...init?.headers },
  });

  const text = await res.text();
  const body = text ? safeJsonParse(text) : undefined;

  if (!res.ok) {
    const msg =
      typeof body === "object" && body && "detail" in (body as any)
        ? String((body as any).detail)
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
