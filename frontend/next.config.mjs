const backendUrl = process.env.ATLAS_BACKEND_URL || "http://127.0.0.1:8080";

/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost", "127.0.0.1:3000", "localhost:3000"],
  // /api/* requests are now handled by app/api/[...path]/route.js which
  // proxies them to the Python backend.  The rewrites() entry is no longer
  // needed, and removing it prevents the Turbopack dev-server from also
  // trying to proxy them (which caused ECONNRESET on POST requests).
  serverExternalPackages: [],
};

// Keep backendUrl referenced so the env var is still documented here.
void backendUrl;

export default nextConfig;
