import { screen } from '@testing-library/react'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { ApplicationRow } from '@/types/db'
import type { SupabaseClient } from '@supabase/supabase-js'

const ROWS: ApplicationRow[] = [{
  id: 'a1', user_id: 'u1', cv_id: 'c1', optimized_cv_id: 'c2', url: 'https://acme.com/jobs/1',
  job_text: null, cover_letter: null, qa: {}, changes: [], status: 'submitted',
  created_at: '2026-07-20T00:00:00Z',
}]
vi.mock('@/lib/db', () => ({ listApplications: vi.fn(async () => ROWS) }))

import { RecentApplications } from '@/components/apply/RecentApplications'

it('lists recent applications with their status', async () => {
  renderWithIntl(<RecentApplications supabase={{} as SupabaseClient} />)
  expect(await screen.findByText(/acme.com/)).toBeInTheDocument()
  expect(screen.getByText('Gönderildi')).toBeInTheDocument()
})
