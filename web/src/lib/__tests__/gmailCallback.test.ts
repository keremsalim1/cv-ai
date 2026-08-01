import { describe, expect, it } from 'vitest'
import { NextRequest } from 'next/server'

import { GET } from '@/app/auth/gmail/callback/route'

function land(query: string): URL {
  const res = GET(new NextRequest(`http://localhost:3000/auth/gmail/callback${query}`))
  return new URL(res.headers.get('location') as string)
}

describe('the Gmail OAuth landing route', () => {
  it('hands the code and state to the applications page', () => {
    const target = land('?code=abc&state=st-1')
    expect(target.pathname).toBe('/applications')
    expect(target.searchParams.get('gmail_code')).toBe('abc')
    expect(target.searchParams.get('gmail_state')).toBe('st-1')
  })

  it('reports a refused consent rather than a broken page', () => {
    expect(land('?error=access_denied').searchParams.get('gmail')).toBe('denied')
  })

  it('treats a missing code as a refusal', () => {
    const target = land('')
    expect(target.searchParams.get('gmail')).toBe('denied')
    expect(target.searchParams.get('gmail_code')).toBeNull()
  })

  it('never forwards the code when Google also reported an error', () => {
    // Both present is not a case Google documents; refusing is the safe read.
    const target = land('?code=abc&error=access_denied')
    expect(target.searchParams.get('gmail_code')).toBeNull()
    expect(target.searchParams.get('gmail')).toBe('denied')
  })

  it('stays on this origin, whatever the redirect claims', () => {
    expect(land('?code=abc&state=st-1').origin).toBe('http://localhost:3000')
  })
})
