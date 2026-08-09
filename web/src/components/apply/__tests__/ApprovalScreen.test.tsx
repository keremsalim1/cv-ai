import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { OptimizedPayload } from '@/types/api'
import { ApprovalScreen } from '@/components/apply/ApprovalScreen'

const PAYLOAD: OptimizedPayload = {
  job_text: 'Backend developer',
  company: 'Acme',
  title: 'Backend Developer',
  cv: {
    full_name: 'Ada Lovelace', title: null, email: 'ada@x.com', phone: null, location: null,
    summary: 'Engineer', experiences: [], education: [], skills: ['Python'],
    languages: [], certifications: [],
  },
  changes: ['Reordered skills'],
  cover_letter: 'I am excited to apply.',
  form: [
    { id: 'motivation', selector: '/x', label: 'Why us?', type: 'textarea', options: [], option_selectors: [], required: false },
    { id: 'experience', selector: '/y', label: 'Years', type: 'select', options: ['1-3', '3-5'], option_selectors: [], required: true },
  ],
  answers: [
    { field_id: 'motivation', value: 'I love APIs.' },
    { field_id: 'experience', value: '3-5' },
  ],
}

it('renders read-only CV summary, changes and editable answers', () => {
  renderWithIntl(<ApprovalScreen payload={PAYLOAD} canSubmit onSubmit={vi.fn()} onDeliver={vi.fn()} />)
  expect(screen.getByText('Ada Lovelace')).toBeInTheDocument()
  expect(screen.getByText('Reordered skills')).toBeInTheDocument()
  expect((screen.getByDisplayValue('I love APIs.') as HTMLTextAreaElement).value).toBe('I love APIs.')
})

it('submit sends edited answers and cover letter', async () => {
  const onSubmit = vi.fn()
  renderWithIntl(<ApprovalScreen payload={PAYLOAD} canSubmit onSubmit={onSubmit} onDeliver={vi.fn()} />)
  await userEvent.clear(screen.getByDisplayValue('I love APIs.'))
  await userEvent.type(screen.getByLabelText('Why us?'), 'Edited motivation')
  await userEvent.click(screen.getByRole('button', { name: 'Onayla ve Başvur' }))
  const [answers, cover] = onSubmit.mock.calls[0]
  expect(answers).toContainEqual({ field_id: 'motivation', value: 'Edited motivation' })
  expect(typeof cover).toBe('string')
})

it('hides the submit button when canSubmit is false', () => {
  renderWithIntl(<ApprovalScreen payload={PAYLOAD} canSubmit={false} onSubmit={vi.fn()} onDeliver={vi.fn()} />)
  expect(screen.queryByRole('button', { name: 'Onayla ve Başvur' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Sadece bana teslim et' })).toBeInTheDocument()
})

it('lists what the model could not confirm', () => {
  renderWithIntl(<ApprovalScreen
    payload={{ ...PAYLOAD, verification_required: ['Confirm the Acme role was not an internship.'] }}
    canSubmit onSubmit={vi.fn()} onDeliver={vi.fn()} />)
  expect(screen.getByText('Confirm the Acme role was not an internship.')).toBeInTheDocument()
})

it('omits the verification block when there is nothing to confirm', () => {
  renderWithIntl(<ApprovalScreen payload={PAYLOAD} canSubmit onSubmit={vi.fn()} onDeliver={vi.fn()} />)
  expect(screen.queryByTestId('approval-verification')).not.toBeInTheDocument()
})
