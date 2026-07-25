import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, type Mock } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { CvRow } from '@/types/db'

const ROUTER = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }
const PARAMS = new URLSearchParams('')
vi.mock('next/navigation', () => ({ useRouter: () => ROUTER, useSearchParams: () => PARAMS }))

const upload = vi.fn(async () => ({ error: null }))
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) },
    storage: { from: () => ({ upload }) },
  }),
}))

const CVS: CvRow[] = [{
  id: 'c1', user_id: 'u1', file_path: 'u1/a.pdf', is_ats: false, source_cv_id: null,
  created_at: '2026-07-12T00:00:00Z',
  parsed_data: {
    full_name: 'Ada', email: null, phone: null, location: null, summary: null,
    experiences: [], education: [], skills: [], languages: [], certifications: [],
  },
}]

vi.mock('@/lib/db', () => ({ listCvs: vi.fn(async () => CVS), insertCv: vi.fn(async () => ({ id: 'opt' })), insertApplication: vi.fn(async () => ({ id: 'app' })), listApplications: vi.fn(async () => []) }))
vi.mock('@/lib/applications', () => ({ saveApplication: vi.fn(async () => {}) }))
vi.mock('@/lib/api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...orig, applyPrepare: vi.fn(), applySubmit: vi.fn(), atsPdf: vi.fn(async () => new Blob(['%PDF'])),
    assistStart: vi.fn(), assistFill: vi.fn(), assistClose: vi.fn(),
  }
})

import { applyPrepare, applySubmit, assistStart, assistFill, assistClose } from '@/lib/api'
import { saveApplication } from '@/lib/applications'
import OptimizePage from '@/app/(app)/optimize/page'

beforeEach(() => vi.clearAllMocks())

async function fillLinkAndPrepare() {
  await screen.findByLabelText('CV')
  await userEvent.type(screen.getByLabelText('Başvuru linki'), 'https://j.com/1')
  await userEvent.click(screen.getByRole('button', { name: 'Hazırla' }))
}

it('login_required shows the sign-in prompt then retries headed', async () => {
  ;(applyPrepare as Mock)
    .mockResolvedValueOnce({ status: 'login_required' })
    .mockResolvedValueOnce({ status: 'ready', form: [], cv: CVS[0].parsed_data, changes: [], cover_letter: 'cl', answers: [], job_text: 'jt' })
  renderWithIntl(<OptimizePage />)
  await fillLinkAndPrepare()
  await userEvent.click(await screen.findByRole('button', { name: 'Pencerede giriş yap ve devam et' }))
  expect((applyPrepare as Mock).mock.calls[1]).toEqual([CVS[0].parsed_data, 'https://j.com/1', expect.any(String), true])
  await screen.findByText('Başvurmadan önce inceleyin')
})

it('ready → approve → submit saves the application and shows the screenshot', async () => {
  ;(applyPrepare as Mock).mockResolvedValue({
    status: 'ready', form: [], cv: CVS[0].parsed_data, changes: [], cover_letter: 'cl', answers: [], job_text: 'jt',
  })
  ;(applySubmit as Mock).mockResolvedValue({ status: 'submitted', screenshot: 'PNGDATA' })
  renderWithIntl(<OptimizePage />)
  await fillLinkAndPrepare()
  await userEvent.click(await screen.findByRole('button', { name: 'Onayla ve Başvur' }))
  await waitFor(() => expect(saveApplication).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ status: 'submitted' })))
  expect((screen.getByRole('img') as HTMLImageElement).src).toContain('PNGDATA')
})

it('captcha goes straight to delivery mode (no submit button)', async () => {
  ;(applyPrepare as Mock).mockResolvedValue({
    status: 'captcha', form: [], cv: CVS[0].parsed_data, changes: [], cover_letter: 'cl', answers: [], job_text: 'jt',
  })
  renderWithIntl(<OptimizePage />)
  await fillLinkAndPrepare()
  await screen.findByText('Başvurmadan önce inceleyin')
  expect(screen.queryByRole('button', { name: 'Onayla ve Başvur' })).toBeNull()
})

it('form_not_found → assisted apply: fills the live form then finishes', async () => {
  ;(applyPrepare as Mock).mockResolvedValue({
    status: 'form_not_found', form: [], cv: CVS[0].parsed_data, changes: [], cover_letter: 'cl', answers: [], job_text: 'jt',
  })
  ;(assistStart as Mock).mockResolvedValue({ session_id: 'sess-1' })
  ;(assistFill as Mock).mockResolvedValue({
    status: 'filled', field_count: 3, screenshot: 'SHOT', filled: [{ label: 'Motivasyon', value: 'X' }],
  })
  ;(assistClose as Mock).mockResolvedValue(undefined)
  renderWithIntl(<OptimizePage />)
  await fillLinkAndPrepare()
  await userEvent.click(await screen.findByRole('button', { name: 'Asistanlı başvuru' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Formu doldur' }))
  expect(assistFill).toHaveBeenCalledWith('sess-1', CVS[0].parsed_data, expect.any(String))
  expect((await screen.findByRole('img') as HTMLImageElement).src).toContain('SHOT')
  await userEvent.click(screen.getByRole('button', { name: 'Bitir' }))
  await waitFor(() => expect(saveApplication).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ status: 'delivered' })))
  expect(assistClose).toHaveBeenCalledWith('sess-1')
})
