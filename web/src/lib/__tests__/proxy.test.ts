import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'

const getUser = vi.fn()
vi.mock('@supabase/ssr', () => ({
  createServerClient: () => ({ auth: { getUser } }),
}))

import { proxy } from '@/proxy'

function signedIn() {
  getUser.mockResolvedValue({ data: { user: { id: 'u-1' } } })
}

function signedOut() {
  getUser.mockResolvedValue({ data: { user: null } })
}

async function landsOn(path: string): Promise<string | null> {
  const res = await proxy(new NextRequest(`http://localhost:3000${path}`))
  return res.headers.get('location')
}

beforeEach(() => {
  getUser.mockReset()
})

describe('the proxy auth rules', () => {
  it('sends a signed-in visitor from the marketing page to the panel', async () => {
    signedIn()
    expect(await landsOn('/')).toBe('http://localhost:3000/dashboard')
  })

  it('sends a signed-in visitor from the sign-in form to the panel', async () => {
    signedIn()
    expect(await landsOn('/login')).toBe('http://localhost:3000/dashboard')
  })

  it('sends a signed-in visitor from the registration form to the panel', async () => {
    signedIn()
    expect(await landsOn('/register')).toBe('http://localhost:3000/dashboard')
  })

  it('leaves the marketing page alone for a signed-out visitor', async () => {
    signedOut()
    expect(await landsOn('/')).toBeNull()
  })

  it('never bounces a signed-in visitor off the panel', async () => {
    // If /dashboard were ever guest-only, the two rules would loop forever.
    signedIn()
    expect(await landsOn('/dashboard')).toBeNull()
  })

  it('still sends a signed-out visitor from the panel to sign-in', async () => {
    signedOut()
    expect(await landsOn('/dashboard')).toBe('http://localhost:3000/login')
  })
})
