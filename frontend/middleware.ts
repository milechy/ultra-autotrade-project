// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { NextRequest, NextResponse } from 'next/server'

export function middleware(request: NextRequest) {
  // Detect locale from Accept-Language header, default to 'ja'
  const acceptLang = request.headers.get('accept-language') || ''
  const locale = acceptLang.toLowerCase().startsWith('en') ? 'en' : 'ja'

  const response = NextResponse.next()
  response.headers.set('x-locale', locale)
  return response
}

export const config = {
  matcher: ['/((?!api|_next|.*\\..*).*)'],
}
