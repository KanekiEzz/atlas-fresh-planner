/**
 * Catch-all API proxy route.
 *
 * Replaces the `rewrites()` entry in next.config.mjs so that every
 * /api/* request is forwarded to the Python backend via a genuine
 * Next.js Route Handler.  This avoids the Turbopack dev-server proxy
 * bugs that cause ECONNRESET / "socket hang up" on POST requests.
 */

const BACKEND = process.env.ATLAS_BACKEND_URL || "http://127.0.0.1:8080";

// Headers the proxy must NOT forward upstream (hop-by-hop).
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
]);

async function proxy(request, { params }) {
  const { path } = await params;
  const segments = Array.isArray(path) ? path : [path];
  const targetUrl = `${BACKEND}/api/${segments.join("/")}`;

  // Forward selected request headers, drop hop-by-hop ones.
  const forwardHeaders = new Headers();
  for (const [key, value] of request.headers.entries()) {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      forwardHeaders.set(key, value);
    }
  }

  // Read request body for methods that carry one.
  const hasBody = !["GET", "HEAD"].includes(request.method);
  const body = hasBody ? await request.arrayBuffer() : undefined;

  let upstream;
  try {
    upstream = await fetch(targetUrl, {
      method: request.method,
      headers: forwardHeaders,
      body,
      // node-fetch / undici: disable automatic decompression so we
      // forward the backend response exactly as-is.
      ...(typeof globalThis.EdgeRuntime === "undefined" && { compress: false }),
    });
  } catch (err) {
    console.error(`[proxy] fetch error → ${targetUrl}:`, err.message);
    return new Response(
      JSON.stringify({ ok: false, error: "proxy_error", message: err.message }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }

  // Forward response headers, drop hop-by-hop ones.
  const responseHeaders = new Headers();
  for (const [key, value] of upstream.headers.entries()) {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      responseHeaders.set(key, value);
    }
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET     = proxy;
export const POST    = proxy;
export const PUT     = proxy;
export const PATCH   = proxy;
export const DELETE  = proxy;
export const OPTIONS = proxy;
export const HEAD    = proxy;
