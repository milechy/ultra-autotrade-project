// Ultra AutoTrade Service Worker
// Cache strategy: Network-first for API, Cache-first for static assets

const CACHE_NAME = 'ultra-autotrade-v1'
const STATIC_CACHE = 'ultra-autotrade-static-v1'

// Static assets to precache
const PRECACHE_URLS = [
  '/',
  '/user/dashboard',
  '/user/approve',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
]

// Install: precache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE_URLS))
  )
  self.skipWaiting()
})

// Activate: clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME && key !== STATIC_CACHE)
          .map((key) => caches.delete(key))
      )
    )
  )
  self.clients.claim()
})

// Fetch strategy
self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  // Skip non-GET and cross-origin requests
  if (request.method !== 'GET' || url.origin !== self.location.origin) return

  // API requests: Network-first, no cache
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/')) {
    event.respondWith(fetch(request))
    return
  }

  // Next.js internals: network only
  if (url.pathname.startsWith('/_next/')) {
    event.respondWith(
      fetch(request).then((res) => {
        // Cache versioned static chunks
        if (url.pathname.includes('/_next/static/')) {
          const responseClone = res.clone()
          caches.open(STATIC_CACHE).then((cache) => cache.put(request, responseClone))
        }
        return res
      }).catch(() => caches.match(request))
    )
    return
  }

  // HTML pages: Network-first with cache fallback
  if (request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const responseClone = res.clone()
          caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone))
          return res
        })
        .catch(() => caches.match(request))
    )
    return
  }

  // Static assets: Cache-first
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached
      return fetch(request).then((res) => {
        const responseClone = res.clone()
        caches.open(STATIC_CACHE).then((cache) => cache.put(request, responseClone))
        return res
      })
    })
  )
})

// Push notification handler
self.addEventListener('push', (event) => {
  if (!event.data) return
  let data
  try {
    data = event.data.json()
  } catch {
    data = { title: 'Ultra AutoTrade', body: event.data.text() }
  }
  event.waitUntil(
    self.registration.showNotification(data.title || 'Ultra AutoTrade', {
      body: data.body || '',
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      tag: data.tag || 'ultra-autotrade',
      data: { url: data.url || '/user/dashboard' },
    })
  )
})

// Notification click: open/focus the app
self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const targetUrl = event.notification.data?.url || '/user/dashboard'
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(targetUrl)
          return client.focus()
        }
      }
      return clients.openWindow(targetUrl)
    })
  )
})
