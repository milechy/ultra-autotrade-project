#!/usr/bin/env node
/**
 * cf-pages-postbuild.js
 *
 * Runs after `next build` when CF_PAGES=1 (Cloudflare Pages environment).
 * Restores all files modified by cf-pages-prebuild.js.
 *
 * This ensures the git working tree is clean and the source files are
 * unchanged after the Cloudflare Pages build completes.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

function log(msg) {
  console.log(`[cf-pages-postbuild] ${msg}`);
}

// 1. Restore app/api/
const apiDir = path.join(ROOT, 'app', 'api');
const apiSkipDir = path.join(ROOT, 'app', '_api_cf_skip');
if (fs.existsSync(apiSkipDir)) {
  if (fs.existsSync(apiDir)) {
    fs.rmSync(apiDir, { recursive: true });
  }
  fs.renameSync(apiSkipDir, apiDir);
  log('Restored app/api/ from app/_api_cf_skip/');
}

// 2. Restore lib/i18n.ts
const i18nPath = path.join(ROOT, 'lib', 'i18n.ts');
const i18nBackup = path.join(ROOT, 'lib', 'i18n.ts.cf_bak');
if (fs.existsSync(i18nBackup)) {
  fs.copyFileSync(i18nBackup, i18nPath);
  fs.unlinkSync(i18nBackup);
  log('Restored lib/i18n.ts');
}

// 3. Restore middleware.ts
const middlewarePath = path.join(ROOT, 'middleware.ts');
const middlewareBackup = path.join(ROOT, 'middleware.ts.cf_bak');
if (fs.existsSync(middlewareBackup)) {
  fs.copyFileSync(middlewareBackup, middlewarePath);
  fs.unlinkSync(middlewareBackup);
  log('Restored middleware.ts');
}

// 4. Restore force-dynamic pages
function findBackups(dir) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...findBackups(fullPath));
    } else if (entry.isFile() && entry.name.endsWith('.cf_bak')) {
      results.push(fullPath);
    }
  }
  return results;
}

const appDir = path.join(ROOT, 'app');
const backups = findBackups(appDir);
for (const backupPath of backups) {
  const originalPath = backupPath.replace(/\.cf_bak$/, '');
  fs.copyFileSync(backupPath, originalPath);
  fs.unlinkSync(backupPath);
}
if (backups.length > 0) {
  log(`Restored ${backups.length} page/layout file(s) with force-dynamic`);
}

// 5. Restore dynamic route page directories
const dynamicRouteDirs = [
  path.join(ROOT, 'app', 'r', '[code]'),
  path.join(ROOT, 'app', '(partner)', 'partner', 'users', '[id]'),
  path.join(ROOT, 'app', '(partner)', 'partner', 'referral', '[id]'),
];
for (const originalDir of dynamicRouteDirs) {
  const parentDir = path.dirname(originalDir);
  const dirName = path.basename(originalDir);
  const skipName = `_cf_skip_${dirName.replace(/[\[\]\.]/g, '_')}`;
  const skipPath = path.join(parentDir, skipName);
  if (fs.existsSync(skipPath)) {
    if (fs.existsSync(originalDir)) {
      fs.rmSync(originalDir, { recursive: true });
    }
    fs.renameSync(skipPath, originalDir);
    log(`Restored ${path.relative(ROOT, originalDir)}`);
  }
}

log('Postbuild complete. Source tree restored to original state.');
