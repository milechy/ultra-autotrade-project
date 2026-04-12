/** @type {import('next').NextConfig} */
const backendUrl = process.env.NEXT_PUBLIC_BACKEND_BASE_URL || '';
const cspConnectSrc = [
  "'self'",
  backendUrl,
  "https://*.infura.io",
  "https://*.alchemy.com",
  "wss://*.walletconnect.org",
  "https://api.coingecko.com",
  "https:",
].filter(Boolean).join(' ');

const createNextIntlPlugin = require('next-intl/plugin');
const withNextIntl = createNextIntlPlugin('./lib/i18n.ts');
const withPWA = require('next-pwa')({
  dest: 'public',
  register: true,
  skipWaiting: true,
  disable: process.env.NODE_ENV === 'development',
  exclude: [
    /app-build-manifest\.json$/,
    /build-manifest\.json$/,
    /middleware-manifest\.json$/,
    /react-loadable-manifest\.json$/,
  ],
});

// PWA configuration (manual SW — no next-pwa package required)
// sw.js is served from /public/sw.js
// Registration is handled by frontend/lib/pwa/register.ts

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  productionBrowserSourceMaps: false,
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production' ? { exclude: ['error', 'warn'] } : false,
  },
  output: 'standalone',
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
  webpack: (config, { isServer, dev }) => {
    config.resolve.fallback = {
      ...config.resolve.fallback,
      '@coinbase/wallet-sdk': false,
      '@metamask/sdk': false,
      '@safe-global/safe-apps-sdk': false,
      '@base-org/account': false,
      'pino-pretty': false,
      '@safe-global/safe-apps-provider': false,
    };
    // Privy の optional な Solana / Farcaster 依存をスタブ（未使用）
    // porto は package.json から削除済み。wagmi/connectors 内部参照をスタブ化
    config.resolve.alias = {
      ...config.resolve.alias,
      '@solana/wallet-adapter-react': false,
      '@farcaster/miniapp-sdk': false,
      'porto': false,
      'porto/internal': false,
    };
    if (!dev && !isServer) {
      config.optimization = {
        ...config.optimization,
        minimize: true,
      };
    }
    return config;
  },
  async headers() {
    return [
      {
        source: '/sw.js',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=0, must-revalidate' },
          { key: 'Service-Worker-Allowed', value: '/' },
        ],
      },
      {
        source: '/manifest.json',
        headers: [
          { key: 'Content-Type', value: 'application/manifest+json' },
          { key: 'Cache-Control', value: 'public, max-age=3600' },
        ],
      },
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-eval' 'unsafe-inline' https://static.cloudflareinsights.com",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "style-src-elem 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "img-src 'self' data: blob:",
              "font-src 'self' https://fonts.gstatic.com",
              `connect-src ${cspConnectSrc}`,
              "frame-ancestors 'none'",
              "worker-src 'self' blob:",
            ].join('; '),
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
        ],
      },
    ]
  },
};
module.exports = withNextIntl(withPWA(nextConfig));
