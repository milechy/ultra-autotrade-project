// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { NextRequest, NextResponse } from 'next/server'

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || ''

function buildUrl(params: { path: string[] }, request: NextRequest) {
  const path = params.path.join('/')
  const url = `${BACKEND_BASE_URL.replace(/\/$/, '')}/api/transactions/${path}`
  const searchParams = request.nextUrl.searchParams.toString()
  return searchParams ? `${url}?${searchParams}` : url
}

function getHeaders(request: NextRequest): Record<string, string> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const auth = request.headers.get('authorization')
  if (auth) headers['Authorization'] = auth
  return headers
}

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  if (!BACKEND_BASE_URL) return NextResponse.json({ detail: 'BACKEND_BASE_URL is not set' }, { status: 500 })
  try {
    const response = await fetch(buildUrl(params, request), { headers: getHeaders(request) })
    const buf = await response.arrayBuffer()
    return new NextResponse(buf, { status: response.status, headers: { 'Content-Type': response.headers.get('content-type') || 'application/json' } })
  } catch {
    return NextResponse.json({ detail: 'Backend unavailable' }, { status: 502 })
  }
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  if (!BACKEND_BASE_URL) return NextResponse.json({ detail: 'BACKEND_BASE_URL is not set' }, { status: 500 })
  try {
    const body = await request.text()
    const response = await fetch(buildUrl(params, request), { method: 'POST', headers: { ...getHeaders(request), 'Content-Type': 'application/json' }, body })
    const buf = await response.arrayBuffer()
    return new NextResponse(buf, { status: response.status, headers: { 'Content-Type': response.headers.get('content-type') || 'application/json' } })
  } catch {
    return NextResponse.json({ detail: 'Backend unavailable' }, { status: 502 })
  }
}
