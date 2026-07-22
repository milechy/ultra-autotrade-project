#!/usr/bin/env node
/**
 * 消費者向け UI に DeFi プロトコル名 / 個別プロダクト名が出ていないか検査する CI ガード。
 *
 * 背景（2026-07-23）:
 *   「Aave」「Pendle」等の名称は消費者向け画面に出さない、という運用ルールがある。
 *   しかし PR #993 で追加した運用方針セレクタと リスク開示モーダルに `Aave USDC 供給のみ` /
 *   `Aave + Pendle PT` / `yoUSD` がそのまま入り、staging-v4 の実機目視で発覚した。
 *   同じ抽象化語彙（`Strategies.optimizer.protocol`）が既にあったのに使われていなかった。
 *   レビューの注意力では防げないので機械で突合する。
 *
 * 判定（fail-closed）:
 *   messages/{ja,en}.json のうち **消費者向けスコープ**（CONSUMER_SCOPES）配下の文字列に
 *   禁止語（BANNED）が含まれていたら FAIL。
 *   管理者 / パートナー向けスコープ（AdminProtocols 等）は運用上むしろ実名が必要なので対象外。
 *
 * 終了コード: 0=クリーン / 1=違反あり
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')

/** 消費者（エンドユーザー）が見る i18n スコープ。ここに実プロトコル名を出さない。 */
const CONSUMER_SCOPES = ['Liff', 'AggressiveDisclosure']

/** 禁止語。大文字小文字は区別しない。 */
const BANNED = ['aave', 'pendle', 'lido', 'steth', 'yousd', 'morpho', 'compound']

const LOCALES = ['ja', 'en']

const violations = []

for (const locale of LOCALES) {
  const file = join(ROOT, 'messages', `${locale}.json`)
  const data = JSON.parse(readFileSync(file, 'utf8'))

  for (const scope of CONSUMER_SCOPES) {
    if (!(scope in data)) continue
    walk(data[scope], [scope], locale)
  }
}

function walk(node, path, locale) {
  if (typeof node === 'string') {
    const lower = node.toLowerCase()
    const hit = BANNED.find((w) => lower.includes(w))
    if (hit) {
      violations.push({ locale, key: path.join('.'), word: hit, text: node })
    }
    return
  }
  if (node && typeof node === 'object') {
    for (const [k, v] of Object.entries(node)) walk(v, [...path, k], locale)
  }
}

if (violations.length === 0) {
  console.log(
    `✅ 消費者向け文言にプロトコル名なし（検査スコープ: ${CONSUMER_SCOPES.join(', ')} / ${LOCALES.join(', ')}）`,
  )
  process.exit(0)
}

console.error('❌ FAIL: 消費者向け文言に DeFi プロトコル名 / プロダクト名が含まれています。')
console.error('')
for (const v of violations) {
  console.error(`  [${v.locale}] ${v.key}`)
  console.error(`    禁止語: "${v.word}"`)
  console.error(`    文言  : ${v.text}`)
}
console.error('')
console.error('  → 機能で説明する言い回しに直してください（例: "満期まで預けて利回りを固定"）。')
console.error('  → 既存の抽象化語彙は messages/*.json の Strategies.optimizer.protocol にあります。')
console.error('  → 管理者向け画面（AdminProtocols 等）は対象外です。実名が必要ならそちらへ。')
process.exit(1)
