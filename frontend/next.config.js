/** @type {import('next').NextConfig} */
// CF_PAGES=1 is injected by Cloudflare Pages automatically.
// When building for CF Pages (demo static export), output is switched to 'export'.
// API routes and server-only pages are excluded by the prebuild script
// (scripts/cf-pages-prebuild.js) which runs before next build.
const isCFPages = process.env.CF_PAGES === '1';
const backendUrl = process.env.NEXT_PUBLIC_API_URL || '';
// AI 判定のリアルタイム配信は wss://<api-host>/api/ai/ws/decisions に接続する
// (liff-chat/page.tsx の WebSocket)。connect-src に wss 版が無いと CSP がブロックし、
// AI判定カードがリアルタイム更新されない (初期 fetch にフォールバックするため一見動くが
// realtime push が静かに死ぬ)。https の API ホストと同一オリジンの wss を明示的に許可する。
// NOTE: connect-src の "https:" ワイルドカードは wss スキームを許可しない。
const wssBackendUrl = backendUrl ? backendUrl.replace(/^https?:\/\//, 'wss://') : '';
const cspConnectSrc = [
  "'self'",
  backendUrl,
  wssBackendUrl,
  "https://api.ultra-auto-trade.com",
  "wss://api.ultra-auto-trade.com",
  "https://api-staging.ultra-auto-trade.com",
  "wss://api-staging.ultra-auto-trade.com",
  "https://*.infura.io",
  "https://*.alchemy.com",
  "wss://*.walletconnect.org",
  "wss://relay.walletconnect.com",
  "wss://relay.walletconnect.org",
  "wss://www.walletconnect.com",
  "https://explorer-api.walletconnect.com",
  "https://api.coingecko.com",
  "https://auth.privy.io",
  "https://*.privy.io",
  "https://api.privy.io",
  "https://telemetry.privy.io",
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
  output: isCFPages ? 'export' : 'standalone',
  ...(isCFPages ? { images: { unoptimized: true } } : {}),
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
    // @stripe/crypto は react-auth 3.29 の FiatOnrampScreen(Stripe Bridge onramp)用の
    // optional peer dep。日本は Deposit address 方式で Stripe Bridge は未使用のためスタブ化。
    config.resolve.alias = {
      ...config.resolve.alias,
      '@solana/wallet-adapter-react': false,
      '@farcaster/miniapp-sdk': false,
      '@stripe/crypto': false,
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
  // headers() is not supported with output:'export' (CF Pages uses public/_headers instead)
  ...(!isCFPages ? {
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
                // LINE LIFF SDK は static.line-scdn.net から client features 拡張
                // (non-ios-extensions 等) を読む。許可しないと liff.init() が
                // 「Unable to load client features」で失敗する（LINE アプリ内 WebView も CSP 準拠）。
                "script-src 'self' 'unsafe-eval' 'unsafe-inline' https://static.cloudflareinsights.com https://auth.privy.io https://static.line-scdn.net",
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://auth.privy.io",
                "style-src-elem 'self' 'unsafe-inline' https://fonts.googleapis.com https://auth.privy.io",
                // LIFF プロフィール画像は *.line-scdn.net 配信。
                "img-src 'self' data: blob: https://auth.privy.io https://*.privy.io https://imagedelivery.net https://*.line-scdn.net",
                "font-src 'self' https://fonts.gstatic.com",
                `connect-src ${cspConnectSrc}`,
                "frame-src 'self' https://auth.privy.io https://verify.walletconnect.com https://verify.walletconnect.org",
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
  } : {}),
};
module.exports = withNextIntl(withPWA(nextConfig));
