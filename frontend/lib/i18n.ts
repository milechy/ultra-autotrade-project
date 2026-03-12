import { getRequestConfig } from 'next-intl/server'
import { headers } from 'next/headers'

export default getRequestConfig(async () => {
  const headersList = headers()
  const locale = headersList.get('x-locale') || 'ja'
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  }
})
