import { NextRequest, NextResponse } from 'next/server'

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || ''

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  if (!BACKEND_BASE_URL) {
    return NextResponse.json({ detail: 'BACKEND_BASE_URL is not set' }, { status: 500 })
  }

  const path = params.path.join('/')
  const url = `${BACKEND_BASE_URL.replace(/\/$/, '')}/api/automation/${path}`
  const searchParams = request.nextUrl.searchParams.toString()
  const fullUrl = searchParams ? `${url}?${searchParams}` : url

  try {
    const response = await fetch(fullUrl, {
      headers: {
        'Accept': 'application/json',
      },
    })
    const buf = await response.arrayBuffer()
    return new NextResponse(buf, {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('content-type') || 'application/json',
      },
    })
  } catch (e: any) {
    return NextResponse.json(
      { detail: `Failed to reach backend: ${e?.message || String(e)}` },
      { status: 502 }
    )
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  if (!BACKEND_BASE_URL) {
    return NextResponse.json({ detail: 'BACKEND_BASE_URL is not set' }, { status: 500 })
  }

  const path = params.path.join('/')
  const url = `${BACKEND_BASE_URL.replace(/\/$/, '')}/api/automation/${path}`

  try {
    const body = await request.text()
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      body,
    })
    const buf = await response.arrayBuffer()
    return new NextResponse(buf, {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('content-type') || 'application/json',
      },
    })
  } catch (e: any) {
    return NextResponse.json(
      { detail: `Failed to reach backend: ${e?.message || String(e)}` },
      { status: 502 }
    )
  }
}
