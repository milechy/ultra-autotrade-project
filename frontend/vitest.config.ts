// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/vitest.config.ts
//
// フロントエンド unit test 基盤 (2026-08-05 導入)。
//
// 背景: これまでフロントエンドのテストは Playwright E2E のみで、
// lib/ 配下のロジック (Web Push 購読のロールバック処理等) を直接検証できなかった。
// E2E は実サーバ + 認証済みセッションを要するため、未認証環境では skip され、
// ロジックの分岐が実質未検証のまま残っていた。
//
// 方針:
// - **ファイル名の拡張子で棲み分ける**:
//     `*.spec.ts` → Playwright (E2E。現在 e2e/ と tests/ の2箇所に存在する)
//     `*.test.ts` → vitest    (unit)
//   ディレクトリ指定で除外すると Playwright の spec 置き場が増えた時に
//   vitest がそれを拾って壊れる (実際 e2e/ だけ除外した初回設定で tests/ を
//   拾って失敗した)。拡張子ベースなら置き場所が増えても壊れない。
// - jsdom 環境: navigator / window / atob 等のブラウザ API を使うコードを検証するため。
// - `@/` エイリアスは tsconfig.json の paths ({"@/*": ["./*"]}) と一致させる。

import { defineConfig } from "vitest/config"
import { fileURLToPath } from "node:url"

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules/**", ".next/**"],
    restoreMocks: true,
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./", import.meta.url)),
    },
  },
})
