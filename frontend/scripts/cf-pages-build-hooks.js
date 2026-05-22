#!/usr/bin/env node
/**
 * cf-pages-build-hooks.js
 *
 * Wrapper that runs cf-pages-prebuild.js or cf-pages-postbuild.js based on --phase arg.
 * Called from package.json prebuild/postbuild scripts to avoid shell quote escaping issues.
 *
 * Usage:
 *   node scripts/cf-pages-build-hooks.js pre
 *   node scripts/cf-pages-build-hooks.js post
 *
 * Only runs when CF_PAGES=1 (Cloudflare Pages build environment).
 */

const path = require('path');
const phase = process.argv[2]; // 'pre' or 'post'

if (process.env.CF_PAGES === '1') {
  if (phase === 'pre') {
    require('./cf-pages-prebuild.js');
  } else if (phase === 'post') {
    require('./cf-pages-postbuild.js');
  } else {
    console.error('[cf-pages-build-hooks] Unknown phase:', phase);
    process.exit(1);
  }
} else {
  // Not a CF Pages build — no-op
  if (phase === 'pre') {
    console.log('[cf-pages-build-hooks] prebuild: not CF_PAGES, skipping');
  }
}
