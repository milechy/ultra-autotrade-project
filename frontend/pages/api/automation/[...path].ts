import type { NextApiRequest, NextApiResponse } from "next";

/**
 * Proxy /api/automation/* to the backend FastAPI.
 *
 * Why:
 * - Avoid browser CORS requirements during local development
 * - Keep UI contract-safe (no backend changes)
 *
 * Configure:
 *   BACKEND_BASE_URL=http://localhost:8000
 */
export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  const backendBase = process.env.BACKEND_BASE_URL;
  if (!backendBase) {
    res.status(500).json({ detail: "BACKEND_BASE_URL is not set" });
    return;
  }

  const pathParts = req.query.path;
  const path = Array.isArray(pathParts) ? pathParts.join("/") : String(pathParts || "");
  const qs = req.url?.includes("?") ? req.url.substring(req.url.indexOf("?")) : "";
  const target = `${backendBase.replace(/\/$/, "")}/api/automation/${path}${qs}`;

  try {
    const upstream = await fetch(target, {
      method: req.method || "GET",
      headers: {
        "Accept": "application/json",
      },
    });

    const buf = await upstream.arrayBuffer();
    res.status(upstream.status);
    res.setHeader("content-type", upstream.headers.get("content-type") || "application/json");
    res.send(Buffer.from(buf));
  } catch (e: any) {
    res.status(502).json({ detail: `Failed to reach backend: ${e?.message || String(e)}` });
  }
}
