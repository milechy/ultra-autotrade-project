#!/usr/bin/env node
/**
 * 消費者向け UI に DeFi プロトコル名 / 個別プロダクト名が出ていないか検査する CI ガード。
 *
 * 背景（2026-07-23）:
 *   「Aave」「Pendle」等の名称は消費者向け画面に出さない運用ルールがある。
 *   PR #993 の運用方針セレクタ / リスク開示モーダルに実名が混入し、staging-v4 の実機
 *   目視で発覚。初版ガードは「i18n の allowlist スコープのみ」を見ており、
 *   (a) `.tsx` の JSX 直書き literal（例: app/user の "Powered by Aave V3" バッジ）と
 *   (b) allowlist に無い消費者スコープ（例: IdleYieldCard の "Morpho Vaults"）を
 *   素通ししていた（Opus レビュー指摘）。本版は2系統で検査する:
 *
 *   [1] i18n denylist 方式:
 *       messages/{ja,en}.json の **admin/partner/ops 以外の全スコープ**の文字列 value を
 *       走査し、禁止語が含まれたら FAIL。新規スコープを足しても自動で検査対象になる
 *       （allowlist の「登録し忘れ」で漏れない fail-safe な向き）。
 *   [2] .tsx 可視テキスト走査:
 *       消費者ルート（app/(liff) / app/user）の .tsx から、コメント / import 行を除いた
 *       上で「可視テキストとして現れる禁止語」を検出。hook 名（useAaveV3）や型名
 *       （AaveTransaction）は ASCII 単語境界で識別子扱いとなり誤検出しない。
 *
 * 終了コード: 0=クリーン / 1=違反あり
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')

/** 禁止語（大文字小文字を区別しない）。 */
const BANNED = ['aave', 'pendle', 'lido', 'steth', 'yousd', 'morpho', 'compound']

/**
 * i18n の走査対象外スコープ（admin / partner / ops）。
 * ここは運用上むしろ実プロトコル名が必要なので許可する。
 * これ以外の全スコープ（=消費者・共通）は走査する（denylist 方式）。
 * 各スコープが本当に非消費者かは実ルートで確認済み:
 *   AdminProtocols/AdminRebalance/AdminSettingsSystem/AdminDashboardAutomation → app/(admin)
 *   BorrowRatesPanel/PendlePositionCard → app/(admin)/protocols
 *   PartnerProposals → app/(partner)/partner/proposals
 */
const EXCLUDED_SCOPES = new Set([
  'AdminProtocols',
  'AdminRebalance',
  'AdminSettingsSystem',
  'AdminDashboardAutomation',
  'BorrowRatesPanel',
  'PendlePositionCard',
  'PartnerProposals',
])

const LOCALES = ['ja', 'en']

/** 消費者ルートの .tsx を走査する対象ディレクトリ。 */
const CONSUMER_TSX_DIRS = ['app/(liff)', 'app/user']

// ASCII 単語境界つきの禁止語マッチャ。識別子（useAaveV3 / AaveTransaction）は
// 前後が英数字なので除外され、"Aave V3" のような可視テキストのみ拾う。
const BANNED_RE = new RegExp(`(?<![A-Za-z0-9_])(${BANNED.join('|')})(?![A-Za-z0-9_])`, 'i')

const violations = []

// ── [1] i18n denylist 走査 ──
for (const locale of LOCALES) {
  const data = JSON.parse(readFileSync(join(ROOT, 'messages', `${locale}.json`), 'utf8'))
  for (const [scope, node] of Object.entries(data)) {
    if (EXCLUDED_SCOPES.has(scope)) continue
    walkI18n(node, [scope], locale)
  }
}

function walkI18n(node, path, locale) {
  if (typeof node === 'string') {
    const lower = node.toLowerCase()
    const hit = BANNED.find((w) => lower.includes(w))
    if (hit) {
      violations.push({ kind: 'i18n', locale, key: path.join('.'), word: hit, text: node })
    }
    return
  }
  if (node && typeof node === 'object') {
    for (const [k, v] of Object.entries(node)) walkI18n(v, [...path, k], locale)
  }
}

// ── [2] .tsx 可視テキスト走査 ──
for (const dir of CONSUMER_TSX_DIRS) {
  for (const file of walkTsx(join(ROOT, dir))) scanTsx(file)
}

function walkTsx(dir) {
  const out = []
  let entries
  try {
    entries = readdirSync(dir)
  } catch {
    return out // ディレクトリ不在は無視
  }
  for (const name of entries) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) out.push(...walkTsx(full))
    else if (name.endsWith('.tsx')) out.push(full)
  }
  return out
}

function scanTsx(file) {
  const raw = readFileSync(file, 'utf8')
  // ブロックコメントを除去（可視テキストではない）。
  const noBlock = raw.replace(/\/\*[\s\S]*?\*\//g, '')
  const lines = noBlock.split('\n')
  lines.forEach((line, i) => {
    let code = line.replace(/\/\/.*$/, '') // 行コメント除去
    if (/^\s*import\b/.test(code)) return // import 行は識別子なので除外
    // クオート文字列（'..' ".." `..`）を除去する。ユーザーに見えるコピーは必ず i18n の
    // t() 経由なので、.tsx 内のクオート文字列に現れる禁止語は enum 値 / state キー /
    // 内部識別子（例: proposal.protocol === "lido", activeTab === 'aave'）であって
    // 可視テキストではない。残った「クオート外テキスト」= JSX テキストノードのみを検査し、
    // "Powered by Aave V3" のようなハードコード可視バッジだけを拾う。
    code = code
      .replace(/'[^']*'/g, "''")
      .replace(/"[^"]*"/g, '""')
      .replace(/`[^`]*`/g, '``')
    const m = BANNED_RE.exec(code)
    if (m) {
      violations.push({
        kind: 'tsx',
        file: file.replace(ROOT + '/', ''),
        line: i + 1,
        word: m[1].toLowerCase(),
        text: line.trim(),
      })
    }
  })
}

// ── 結果 ──
if (violations.length === 0) {
  console.log(
    `✅ 消費者向けにプロトコル名なし（i18n: admin/partner 以外の全スコープ / .tsx: ${CONSUMER_TSX_DIRS.join(', ')}）`,
  )
  process.exit(0)
}

console.error('❌ FAIL: 消費者向け UI に DeFi プロトコル名 / プロダクト名が含まれています。')
console.error('')
for (const v of violations) {
  if (v.kind === 'i18n') {
    console.error(`  [i18n/${v.locale}] ${v.key}  （禁止語: "${v.word}"）`)
    console.error(`      ${v.text}`)
  } else {
    console.error(`  [tsx] ${v.file}:${v.line}  （禁止語: "${v.word}"）`)
    console.error(`      ${v.text}`)
  }
}
console.error('')
console.error('  → 機能で説明する言い回しに直してください（例: "満期まで預けて利回りを固定"）。')
console.error('  → admin/partner 向けで実名が必要なら EXCLUDED_SCOPES / 対象外ルートで扱ってください。')
process.exit(1)
