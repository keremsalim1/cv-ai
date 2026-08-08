import { vi } from 'vitest'
import type { SupabaseClient } from '@supabase/supabase-js'

const upload = vi.fn(async () => ({ error: null }))
const insertCv = vi.fn(async (..._a: unknown[]) => ({ id: 'opt-cv' }))
const insertApplication = vi.fn(async (..._a: unknown[]) => ({ id: 'app-1' }))
vi.mock('@/lib/db', () => ({ insertCv: (...a: unknown[]) => insertCv(...a), insertApplication: (...a: unknown[]) => insertApplication(...a) }))

import { saveApplication } from '@/lib/applications'

const CV = {
  full_name: 'Ada', email: null, phone: null, location: null, summary: null,
  experiences: [], education: [], skills: [], languages: [], certifications: [],
}

it('uploads the pdf, saves optimized CV (is_ats=false) and records the application', async () => {
  const sb = { storage: { from: () => ({ upload }) } } as unknown as SupabaseClient
  await saveApplication(sb, {
    userId: 'u1', sourceCvId: 'c1', optimizedCv: CV, pdf: new Blob(['%PDF']),
    url: 'https://x', jobText: 'jt', coverLetter: 'cl', form: [], answers: [],
    changes: ['a'], status: 'delivered',
  })
  expect(upload).toHaveBeenCalled()
  expect(insertCv).toHaveBeenCalledWith(sb, expect.objectContaining({
    user_id: 'u1', is_ats: false, source_cv_id: 'c1',
  }))
  expect(insertApplication).toHaveBeenCalledWith(sb, expect.objectContaining({
    user_id: 'u1', cv_id: 'c1', optimized_cv_id: 'opt-cv', status: 'delivered',
  }))
})

it('records the company and title so the application can name itself', async () => {
  // Without these the row reaches the list as "Şirket belirtilmemiş", even
  // though /apply/prepare read both off the posting.
  const sb = { storage: { from: () => ({ upload }) } } as unknown as SupabaseClient
  await saveApplication(sb, {
    userId: 'u1', sourceCvId: 'c1', optimizedCv: CV, pdf: new Blob(['%PDF']),
    url: 'https://x', jobText: 'jt', coverLetter: 'cl', form: [], answers: [],
    changes: ['a'], status: 'delivered',
    company: 'Acme', title: 'Backend Developer',
  })
  expect(insertApplication).toHaveBeenCalledWith(sb, expect.objectContaining({
    company: 'Acme', title: 'Backend Developer',
  }))
})
