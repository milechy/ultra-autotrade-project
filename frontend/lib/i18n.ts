// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// demo/frontend-static: locale 固定 'ja' (next/headers 削除で static export 対応)。
// 本番 (output: 'standalone') は main branch の i18n.ts を使用。
import { getRequestConfig } from 'next-intl/server'

export default getRequestConfig(async () => {
  const locale = 'ja'
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  }
})
