import createMiddleware from 'next-intl/middleware';

export default createMiddleware({
  locales: ['ja', 'en'],
  defaultLocale: 'ja',
  localeDetection: true,
  localePrefix: 'never',
});

export const config = {
  matcher: ['/((?!api|_next|.*\\..*).*)'],
};
