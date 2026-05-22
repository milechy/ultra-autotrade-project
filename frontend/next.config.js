/** @type {import('next').NextConfig} */
// main branch (VPS/Docker 本番): output: 'standalone' で .next/standalone を生成し
// node server として配信。Dockerfile runner 段が COPY --from=builder /app/.next/standalone/ /app/ で参照する。
// output: 'export' (Cloudflare Pages 向け静的書出) は demo/frontend-static ブランチ専用。
// main には export を置かない。
const backendUrl = process.env.NEXT_PUBLIC_BACKEND_BASE_URL || '';
// CSP は public/_headers で配信される。本変数は cspConnectSrc 派生で参照されないが、
// 既存 import 依存性を破壊しないため定義のみ残す。
void backendUrl;

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

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  productionBrowserSourceMaps: false,
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production' ? { exclude: ['error', 'warn'] } : false,
  },
  output: 'standalone',
  images: { unoptimized: true },
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
  // async headers() は static export では無効。CSP / XFO / XCTO / sw.js / manifest.json
  // の Cache-Control は public/_headers (Netlify/Cloudflare Pages 互換) に移行済。
};
module.exports = withNextIntl(withPWA(nextConfig));
