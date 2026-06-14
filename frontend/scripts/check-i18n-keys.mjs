// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/scripts/check-i18n-keys.mjs
//
// i18n キー存在検査 — baseline ratchet 方式（再発防止 / Asana 1215691378757415）。
//
// 背景: i18n wave 系 PR が messages/*.json を全体上書きする運用のため、機能 PR で
// 足した i18n キーが後続 wave に巻き込まれて消える事故が複数回発生（#730 緊急停止
// ボタンの生キー表示）。next-intl はキー未解決時に例外を投げず生キーを描画するため、
// tsc も next build も通過し検出できない。
//
// 仕組み: frontend/app・frontend/components 配下の .ts/.tsx を走査し、
//   - useTranslations("NS") / getTranslations("NS") の namespace
//   - t("literal.key") の静的キー（テンプレートリテラル・${} は静的検証不能のためスキップ）
// を抽出し、各 NS.key が ja.json・en.json の両方に存在するか検証する。
//
// 既存の欠落（admin/web 画面の i18n 負債）は baseline に固定し、CI では
// 「baseline に無い新規欠落」だけを失敗扱いにする（ratchet）。これにより、
// 既存負債で全 PR をブロックせず、かつ「存在したキーが消える」事故（#730 型）は
// 新規欠落として確実に検出する。
//
// 使い方:
//   node scripts/check-i18n-keys.mjs                  # 検査（CI / ローカル）
//   node scripts/check-i18n-keys.mjs --update-baseline # baseline 再生成（負債を直した時）

import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(process.cwd());
const MESSAGES_DIR = path.join(ROOT, "messages");
const BASELINE_PATH = path.join(ROOT, "scripts", "i18n-missing-baseline.json");
const UPDATE = process.argv.includes("--update-baseline");

const ja = JSON.parse(fs.readFileSync(path.join(MESSAGES_DIR, "ja.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(MESSAGES_DIR, "en.json"), "utf8"));

function hasKey(obj, dotted) {
  return (
    dotted
      .split(".")
      .reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), obj) !==
    undefined
  );
}

function walk(dir, acc = []) {
  if (!fs.existsSync(dir)) return acc;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (!["node_modules", ".next", "scripts"].includes(e.name)) walk(p, acc);
    } else if (/\.(tsx?|mts)$/.test(e.name) && !/\.d\.ts$/.test(e.name)) {
      acc.push(p);
    }
  }
  return acc;
}

const files = [...walk(path.join(ROOT, "app")), ...walk(path.join(ROOT, "components"))];

const NS_RE = /(?:useTranslations|getTranslations)\(\s*["'`]([^"'`]+)["'`]\s*\)/g;
const KEY_RE = /\bt\(\s*["']([^"'`$\\]+)["']/g;

// 現状の欠落（一意 "NS.key" の集合）を算出。
const missing = new Set();
for (const file of files) {
  const src = fs.readFileSync(file, "utf8");
  const namespaces = [...src.matchAll(NS_RE)].map((m) => m[1]);
  if (namespaces.length === 0) continue;
  const keys = [...src.matchAll(KEY_RE)].map((m) => m[1]);
  for (const key of keys) {
    const resolved = namespaces.some(
      (ns) => hasKey(ja, `${ns}.${key}`) && hasKey(en, `${ns}.${key}`),
    );
    if (!resolved) missing.add(`${namespaces[0]}.${key}`);
  }
}

const missingSorted = [...missing].sort();

if (UPDATE) {
  fs.writeFileSync(BASELINE_PATH, JSON.stringify(missingSorted, null, 2) + "\n");
  console.log(`✅ baseline 更新: ${missingSorted.length} 件を ${path.relative(ROOT, BASELINE_PATH)} に記録`);
  process.exit(0);
}

const baseline = fs.existsSync(BASELINE_PATH)
  ? new Set(JSON.parse(fs.readFileSync(BASELINE_PATH, "utf8")))
  : new Set();

const newViolations = missingSorted.filter((k) => !baseline.has(k));
const fixed = [...baseline].filter((k) => !missing.has(k)).sort();

if (fixed.length > 0) {
  console.log(
    `ℹ️  baseline の ${fixed.length} 件が解消済み。--update-baseline で baseline を縮小してください:`,
  );
  for (const k of fixed) console.log(`    ${k}`);
}

if (newViolations.length > 0) {
  console.error("\n❌ i18n: baseline に無い新規の欠落キーがあります（wave マージでの消失や打ち間違いの可能性）:");
  for (const k of newViolations) console.error(`    ${k}  [ja:${hasKey(ja, k) ? "✓" : "✗"} en:${hasKey(en, k) ? "✓" : "✗"}]`);
  console.error(
    "\n対応: messages/ja.json・en.json に該当キーを追加（wave で消えた場合は復活）。" +
      "\n意図的に許容する場合のみ `node scripts/check-i18n-keys.mjs --update-baseline` で baseline 更新。",
  );
  process.exit(1);
}

console.log(
  `✅ i18n: 新規の欠落なし（baseline ${baseline.size} 件 / 走査 ${files.length} ファイル）`,
);
