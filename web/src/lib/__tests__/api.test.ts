import { vi, type Mock } from 'vitest'

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: 'tok-123' } } }),
    },
  }),
}))

import { ApiError, fetchJob, parseCv, scoreCv } from '@/lib/api'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const CV = {
  full_name: 'Ada', email: null, phone: null, location: null, summary: null,
  experiences: [], education: [], skills: [], languages: [], certifications: [],
}

beforeEach(() => {
  global.fetch = vi.fn()
})

it('parseCv posts multipart with bearer token and unwraps cv', async () => {
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, { cv: CV }))
  const file = new File([new Uint8Array([1])], 'cv.pdf', { type: 'application/pdf' })
  const cv = await parseCv(file)
  expect(cv.full_name).toBe('Ada')
  const [url, init] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/cv/parse')
  expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok-123')
  expect(init.body).toBeInstanceOf(FormData)
})

it('maps API error codes into ApiError', async () => {
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(400, { detail: { code: 'SCANNED_PDF' } }))
  const file = new File([new Uint8Array([1])], 'cv.pdf', { type: 'application/pdf' })
  await expect(parseCv(file)).rejects.toMatchObject({ code: 'SCANNED_PDF', status: 400 })
})

it('fetchJob sends JSON body', async () => {
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, {
    criteria: { title: 'Dev', company: null, requirements: [], skills: [] },
    description: 'text', fetch_method: 'manual',
  }))
  const out = await fetchJob({ text: 'text' })
  expect(out.fetch_method).toBe('manual')
  const [, init] = (global.fetch as Mock).mock.calls[0]
  expect(JSON.parse(init.body as string)).toEqual({ text: 'text' })
})

it('scoreCv returns the evaluation and non-JSON errors become UNKNOWN', async () => {
  ;(global.fetch as Mock).mockResolvedValue(new Response('boom', { status: 500 }))
  await expect(
    scoreCv(CV, { title: 'Dev', company: null, requirements: [], skills: [] })
  ).rejects.toMatchObject({ code: 'UNKNOWN', status: 500 })
  expect(new ApiError('X', 1)).toBeInstanceOf(Error)
})

it('applyPrepare posts cv+url+language+headed and returns the result', async () => {
  const { applyPrepare } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, {
    status: 'ready', form: [], cv: CV, changes: [], cover_letter: null, answers: [], job_text: 'jt',
  }))
  const out = await applyPrepare(CV, 'https://j.com/1', 'en', true)
  expect(out.status).toBe('ready')
  const [url, init] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/apply/prepare')
  expect(JSON.parse(init.body as string)).toEqual({
    cv: CV, url: 'https://j.com/1', language: 'en', headed: true,
  })
})

it('applySubmit posts answers and defaults headed to false', async () => {
  const { applySubmit } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, { status: 'submitted', screenshot: 'AAA' }))
  const out = await applySubmit(CV, 'https://j.com/1', 'en', [{ field_id: 'x', value: 'y' }])
  expect(out).toMatchObject({ status: 'submitted', screenshot: 'AAA' })
  const [, init] = (global.fetch as Mock).mock.calls[0]
  expect(JSON.parse(init.body as string)).toEqual({
    cv: CV, url: 'https://j.com/1', language: 'en',
    answers: [{ field_id: 'x', value: 'y' }], headed: false,
  })
})

it('assistStart posts the url and returns the session id', async () => {
  const { assistStart } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, { session_id: 'sess-1' }))
  const out = await assistStart('https://j.com/1')
  expect(out.session_id).toBe('sess-1')
  const [url, init] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/apply/assist/start')
  expect(JSON.parse(init.body as string)).toEqual({ url: 'https://j.com/1' })
})

it('assistFill posts session+cv+language', async () => {
  const { assistFill } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, {
    status: 'filled', filled: [{ label: 'Email', value: 'a@b.c' }], field_count: 2, screenshot: 'AAA',
  }))
  const out = await assistFill('sess-1', CV, 'en')
  expect(out).toMatchObject({ status: 'filled', field_count: 2 })
  const [url, init] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/apply/assist/fill')
  expect(JSON.parse(init.body as string)).toEqual({ session_id: 'sess-1', cv: CV, language: 'en' })
})

it('assistClose posts the session id', async () => {
  const { assistClose } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, { ok: true }))
  await assistClose('sess-1')
  const [url, init] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/apply/assist/close')
  expect(JSON.parse(init.body as string)).toEqual({ session_id: 'sess-1' })
})

it('inboxStatus gets the connection state', async () => {
  const { inboxStatus } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, {
    connected: true, email: 'ada@example.com', last_synced_at: null, status: 'active',
  }))
  const out = await inboxStatus()
  expect(out.email).toBe('ada@example.com')
  const [url, init] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/inbox/status')
  expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok-123')
})

it('inboxSync posts and returns what changed', async () => {
  const { inboxSync } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, {
    scanned: 3, classified: 2, created: 1,
    updated: [{ application_id: 'a1', company: 'Acme', from_stage: 'received', to_stage: 'rejected' }],
    partial: false,
  }))
  const out = await inboxSync()
  expect(out.updated[0].to_stage).toBe('rejected')
  const [url, init] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/inbox/sync')
  expect(init.method).toBe('POST')
})

it('inboxConnect posts the code under the name the API expects', async () => {
  const { inboxConnect } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, {
    connected: true, email: 'ada@example.com',
  }))
  await inboxConnect('auth-code', 'http://localhost:3000/auth/gmail/callback')
  const [url, init] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/inbox/connect')
  expect(JSON.parse(init.body as string)).toEqual({
    code: 'auth-code', redirect_uri: 'http://localhost:3000/auth/gmail/callback',
  })
})

it('inboxDisconnect deletes the connection', async () => {
  const { inboxDisconnect } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, { connected: false }))
  await inboxDisconnect()
  const [url, init] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/inbox/connect')
  expect(init.method).toBe('DELETE')
})

it('a revoked grant surfaces as GMAIL_DISCONNECTED', async () => {
  const { inboxSync } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(
    jsonResponse(409, { detail: { code: 'GMAIL_DISCONNECTED' } })
  )
  await expect(inboxSync()).rejects.toMatchObject({ code: 'GMAIL_DISCONNECTED', status: 409 })
})
