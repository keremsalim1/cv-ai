import { vi } from 'vitest'
import {
  findEvaluation, insertApplication, insertCv, listApplicationEvents, listApplications, listCvs,
} from '@/lib/db'
import type { SupabaseClient } from '@supabase/supabase-js'

// Chainable stub: every method returns the stub; awaiting it resolves `result`.
function stubClient(result: unknown) {
  const q: Record<string, unknown> = {}
  for (const m of ['select', 'insert', 'order', 'eq', 'maybeSingle', 'single']) {
    q[m] = vi.fn(() => q)
  }
  ;(q as { then: unknown }).then = (resolve: (v: unknown) => void) => resolve(result)
  const from = vi.fn(() => q)
  return { sb: { from } as unknown as SupabaseClient, from, q }
}

it('listCvs queries cvs newest first', async () => {
  const rows = [{ id: 'c1' }]
  const { sb, from, q } = stubClient({ data: rows, error: null })
  await expect(listCvs(sb)).resolves.toEqual(rows)
  expect(from).toHaveBeenCalledWith('cvs')
  expect(q.order).toHaveBeenCalledWith('created_at', { ascending: false })
})

it('insertCv returns the inserted row', async () => {
  const row = { id: 'c2' }
  const { sb } = stubClient({ data: row, error: null })
  const newCv = {
    user_id: 'u1', file_path: 'u1/a.pdf', is_ats: false, source_cv_id: null,
    parsed_data: {
      full_name: 'Ada', email: null, phone: null, location: null, summary: null,
      experiences: [], education: [], skills: [], languages: [], certifications: [],
    },
  }
  await expect(insertCv(sb, newCv)).resolves.toEqual(row)
})

it('findEvaluation filters by cv and job and can return null', async () => {
  const { sb, q } = stubClient({ data: null, error: null })
  await expect(findEvaluation(sb, 'c1', 'j1')).resolves.toBeNull()
  expect(q.eq).toHaveBeenCalledWith('cv_id', 'c1')
  expect(q.eq).toHaveBeenCalledWith('job_id', 'j1')
})

it('throws on supabase error', async () => {
  const { sb } = stubClient({ data: null, error: new Error('db down') })
  await expect(listCvs(sb)).rejects.toThrow('db down')
})

it('listApplications queries applications newest first', async () => {
  const rows = [{ id: 'a1' }]
  const { sb, from, q } = stubClient({ data: rows, error: null })
  await expect(listApplications(sb)).resolves.toEqual(rows)
  expect(from).toHaveBeenCalledWith('applications')
  expect(q.order).toHaveBeenCalledWith('created_at', { ascending: false })
})

it('insertApplication returns the inserted row', async () => {
  const row = { id: 'a2' }
  const { sb } = stubClient({ data: row, error: null })
  await expect(insertApplication(sb, {
    user_id: 'u1', cv_id: 'c1', optimized_cv_id: 'c2', url: 'https://x', job_text: null,
    cover_letter: null, qa: {}, changes: [], status: 'delivered',
  })).resolves.toEqual(row)
})

it('lists an application\'s events newest first', async () => {
  const { sb, from, q } = stubClient({ data: [{ id: 'e1' }], error: null })

  const rows = await listApplicationEvents(sb, 'app-1')

  expect(from).toHaveBeenCalledWith('application_events')
  expect(q.eq).toHaveBeenCalledWith('application_id', 'app-1')
  expect(q.order).toHaveBeenCalledWith('received_at', { ascending: false })
  expect(rows).toEqual([{ id: 'e1' }])
})
