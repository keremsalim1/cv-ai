import { act, screen } from '@testing-library/react'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import { ProgressBar } from '@/components/ProgressBar'

afterEach(() => {
  vi.useRealTimers()
})

it('shows the label and the bar fills as time passes', () => {
  vi.useFakeTimers()
  const { container } = renderWithIntl(<ProgressBar label="Dönüştürülüyor…" />)
  expect(screen.getByText('Dönüştürülüyor…')).toBeInTheDocument()

  const bar = container.querySelector('[role="status"] div div') as HTMLElement
  const before = parseFloat(bar.style.width)
  act(() => {
    vi.advanceTimersByTime(10_000)
  })
  const after = parseFloat(bar.style.width)
  expect(after).toBeGreaterThan(before)
  expect(after).toBeLessThan(100)
})
