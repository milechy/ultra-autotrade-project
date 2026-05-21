#!/usr/bin/env node
/**
 * cf-pages-prebuild.js
 *
 * Runs before `next build` when CF_PAGES=1 (Cloudflare Pages environment).
 * Prepares the source tree for static export (output: 'export') by:
 *
 * 1. Moving app/api/ → app/_api_cf_skip/
 *    Next.js App Router Route Handlers (API routes) are incompatible with
 *    output:'export'. They must be excluded from the build.
 *
 * 2. Replacing lib/i18n.ts with a static-export-compatible version.
 *    The production i18n.ts uses headers() from next/headers (server-only),
 *    which cannot be statically rendered. The demo version uses fixed 'ja' locale.
 *
 * 3. Replacing middleware.ts with an empty stub.
 *    The production middleware uses next/headers-based locale routing,
 *    which is incompatible with static export.
 *
 * 4. Removing `export const dynamic = 'force-dynamic'` from pages.
 *    Static export cannot coexist with force-dynamic.
 *
 * The companion script cf-pages-postbuild.js restores all modified files.
 *
 * Context: PR #372 reverts PR #335's accidental main merge. CF Pages project
 * ultra-autotrade-demo is configured with root:frontend/ build:npm run build
 * output:out. This script enables that config to work with standalone-first
 * next.config.js (output defaults to 'standalone' for Docker builds).
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

function log(msg) {
  console.log(`[cf-pages-prebuild] ${msg}`);
}

// 1. Move app/api/ → app/_api_cf_skip/
const apiDir = path.join(ROOT, 'app', 'api');
const apiSkipDir = path.join(ROOT, 'app', '_api_cf_skip');
if (fs.existsSync(apiDir)) {
  fs.renameSync(apiDir, apiSkipDir);
  log('Moved app/api/ → app/_api_cf_skip/ (excluded from static export)');
} else {
  log('app/api/ not found — skipping move');
}

// 2. Backup and replace lib/i18n.ts
const i18nPath = path.join(ROOT, 'lib', 'i18n.ts');
const i18nBackup = path.join(ROOT, 'lib', 'i18n.ts.cf_bak');
if (fs.existsSync(i18nPath)) {
  fs.copyFileSync(i18nPath, i18nBackup);
  const staticI18n = `// CF Pages static export version — fixed 'ja' locale (no next/headers)
// Original backed up to lib/i18n.ts.cf_bak by cf-pages-prebuild.js
import { getRequestConfig } from 'next-intl/server'

export default getRequestConfig(async () => {
  return {
    locale: 'ja',
    messages: (await import('../messages/ja.json')).default,
  }
})
`;
  fs.writeFileSync(i18nPath, staticI18n);
  log('Replaced lib/i18n.ts with static-export-compatible version');
}

// 3. Backup and stub middleware.ts
const middlewarePath = path.join(ROOT, 'middleware.ts');
const middlewareBackup = path.join(ROOT, 'middleware.ts.cf_bak');
if (fs.existsSync(middlewarePath)) {
  fs.copyFileSync(middlewarePath, middlewareBackup);
  const stubMiddleware = `// CF Pages static export: middleware stub (locale routing disabled)
// Original backed up to middleware.ts.cf_bak by cf-pages-prebuild.js
export {};
`;
  fs.writeFileSync(middlewarePath, stubMiddleware);
  log('Replaced middleware.ts with empty stub');
}

// 4. Remove 'force-dynamic' from pages
// Find all page.tsx files with force-dynamic and comment it out
function findFiles(dir, ext) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory() && !entry.name.startsWith('_') && entry.name !== 'api') {
      results.push(...findFiles(fullPath, ext));
    } else if (entry.isFile() && entry.name.endsWith(ext)) {
      results.push(fullPath);
    }
  }
  return results;
}

const appDir = path.join(ROOT, 'app');
const pageFiles = findFiles(appDir, 'page.tsx');
const layoutFiles = findFiles(appDir, 'layout.tsx');
const allFiles = [...pageFiles, ...layoutFiles];

let patchedCount = 0;
for (const filePath of allFiles) {
  const content = fs.readFileSync(filePath, 'utf8');
  if (content.includes("export const dynamic = 'force-dynamic'")) {
    const backupPath = filePath + '.cf_bak';
    fs.copyFileSync(filePath, backupPath);
    const patched = content.replace(
      /export const dynamic = 'force-dynamic'\n?/g,
      "// export const dynamic = 'force-dynamic' (disabled for CF Pages static export)\n"
    );
    fs.writeFileSync(filePath, patched);
    patchedCount++;
  }
}
if (patchedCount > 0) {
  log(`Commented out 'force-dynamic' in ${patchedCount} file(s)`);
}

log('Prebuild complete. Run cf-pages-postbuild.js after build to restore files.');
