// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { NextRequest, NextResponse } from 'next/server'

export function middleware(request: NextRequest) {
  // Check cookie first (user explicit choice), then Accept-Language header
  const cookieLocale = request.cookies.get('NEXT_LOCALE')?.value
  let locale = 'ja' // default

  if (cookieLocale === 'en' || cookieLocale === 'ja') {
    locale = cookieLocale
  } else {
    const acceptLang = request.headers.get('accept-language') || ''
    locale = acceptLang.toLowerCase().startsWith('en') ? 'en' : 'ja'
  }

  const response = NextResponse.next()
  response.headers.set('x-locale', locale)
  return response
}

export const config = {
  matcher: ['/((?!api|_next|.*\\..*).*)'],
}
