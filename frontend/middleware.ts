// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { NextRequest, NextResponse } from 'next/server'

export function middleware(request: NextRequest) {
  // Locale source: explicit NEXT_LOCALE cookie only (user's in-app choice via useLanguage).
  // Accept-Language is intentionally NOT used: this is a Japan-primary app, and when
  // liff.openWindow({external:true}) opens /terms or /privacy-policy in the device's
  // default browser, that browser does not share cookies with LINE's WebView.
  // Relying on Accept-Language showed English to Japanese users whose external browser
  // is English-primary. Default is 'ja' unless user explicitly toggled via setLanguage().
  const cookieLocale = request.cookies.get('NEXT_LOCALE')?.value
  const locale = (cookieLocale === 'en' || cookieLocale === 'ja') ? cookieLocale : 'ja'

  const response = NextResponse.next()
  response.headers.set('x-locale', locale)
  return response
}

export const config = {
  matcher: ['/((?!api|_next|.*\\..*).*)'],
}
