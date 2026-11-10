/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Proxy API calls through the Next server so the browser only needs one address (no CORS, works in previews).
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/(.*)", headers: [
      { key: "X-Frame-Options", value: "DENY" },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "no-referrer" },
    ] }];
  },
};
export default nextConfig;
