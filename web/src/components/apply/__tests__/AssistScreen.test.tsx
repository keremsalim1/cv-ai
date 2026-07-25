import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { AssistFillResult } from '@/types/api'
import { AssistScreen } from '@/components/apply/AssistScreen'

const FILLED: AssistFillResult = {
  status: 'filled', field_count: 2, screenshot: 'PNGDATA',
  filled: [{ label: 'Motivasyon', value: 'API severim' }],
}

it('fill button triggers onFill', async () => {
  const onFill = vi.fn()
  renderWithIntl(<AssistScreen result={null} busy={false} onFill={onFill} onFinish={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'Formu doldur' }))
  expect(onFill).toHaveBeenCalled()
})

it('shows the filled summary and screenshot', () => {
  renderWithIntl(<AssistScreen result={FILLED} busy={false} onFill={vi.fn()} onFinish={vi.fn()} />)
  expect(screen.getByText(/2 alan dolduruldu/)).toBeInTheDocument()
  expect(screen.getByText(/API severim/)).toBeInTheDocument()
  expect((screen.getByRole('img') as HTMLImageElement).src).toContain('PNGDATA')
})

it('shows the no-form notice', () => {
  renderWithIntl(<AssistScreen result={{ status: 'no_form' }} busy={false} onFill={vi.fn()} onFinish={vi.fn()} />)
  expect(screen.getByText(/form bulunamadı/)).toBeInTheDocument()
})

it('finish button triggers onFinish', async () => {
  const onFinish = vi.fn()
  renderWithIntl(<AssistScreen result={null} busy={false} onFill={vi.fn()} onFinish={onFinish} />)
  await userEvent.click(screen.getByRole('button', { name: 'Bitir' }))
  expect(onFinish).toHaveBeenCalled()
})
