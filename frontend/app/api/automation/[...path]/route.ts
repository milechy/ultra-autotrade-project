// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
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
  const authorization = request.headers.get('authorization')

  try {
    const response = await fetch(fullUrl, {
      headers: {
        'Accept': 'application/json',
        ...(authorization ? { 'Authorization': authorization } : {}),
      },
    })
    const buf = await response.arrayBuffer()
    return new NextResponse(buf, {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('content-type') || 'application/json',
      },
    })
  } catch {
    return NextResponse.json(
      { detail: 'Backend unavailable' },
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
  const authorization = request.headers.get('authorization')

  try {
    const body = await request.text()
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        ...(authorization ? { 'Authorization': authorization } : {}),
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
  } catch {
    return NextResponse.json(
      { detail: 'Backend unavailable' },
      { status: 502 }
    )
  }
}
