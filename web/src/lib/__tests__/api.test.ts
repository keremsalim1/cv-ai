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
