import { vi } from 'vitest'
import { findEvaluation, insertCv, listCvs } from '@/lib/db'
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
