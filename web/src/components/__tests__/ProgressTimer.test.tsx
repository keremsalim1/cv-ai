import { act, screen } from '@testing-library/react'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import { ProgressTimer } from '@/components/ProgressTimer'

afterEach(() => {
  vi.useRealTimers()
})

it('shows the label and counts elapsed seconds', () => {
  vi.useFakeTimers()
  renderWithIntl(<ProgressTimer label="Dönüştürülüyor…" />)
  expect(screen.getByText('Dönüştürülüyor…')).toBeInTheDocument()
  expect(screen.getByText('0 sn')).toBeInTheDocument()
  act(() => {
    vi.advanceTimersByTime(3000)
  })
  expect(screen.getByText('3 sn')).toBeInTheDocument()
})
