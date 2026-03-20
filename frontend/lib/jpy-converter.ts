const CACHE_TTL_MS = 5 * 60 * 1000

let cachedRate: number | null = null
let cachedAt = 0

async function getUSDCtoJPYRate(): Promise<number> {
  const now = Date.now()
  if (cachedRate !== null && now - cachedAt < CACHE_TTL_MS) {
    return cachedRate
  }
  try {
    const res = await fetch(
      'https://api.coingecko.com/api/v3/simple/price?ids=usd-coin&vs_currencies=jpy'
    )
    if (!res.ok) throw new Error(`CoinGecko HTTP ${res.status}`)
    const data = (await res.json()) as { 'usd-coin': { jpy: number } }
    cachedRate = data['usd-coin'].jpy
    cachedAt = now
    return cachedRate
  } catch {
    return 155 // fallback rate
  }
}

export async function convertUSDCtoJPY(amount: number): Promise<number> {
  const rate = await getUSDCtoJPYRate()
  return amount * rate
}

export function formatJPY(amount: number): string {
  return `¥${Math.round(amount).toLocaleString('ja-JP')}`
}
