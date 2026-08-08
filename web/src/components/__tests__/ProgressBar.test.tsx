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

  // The fill is a scaleX transform, not a width — growing it must not cost layout.
  const bar = container.querySelector('[role="status"] div div') as HTMLElement
  const scaleOf = (el: HTMLElement) => parseFloat(el.style.transform.match(/scaleX\(([\d.]+)\)/)![1])

  const before = scaleOf(bar)
  act(() => {
    vi.advanceTimersByTime(10_000)
  })
  const after = scaleOf(bar)
  expect(after).toBeGreaterThan(before)
  expect(after).toBeLessThan(1)
})

it('shows the high-demand notice after 60 seconds', () => {
  vi.useFakeTimers()
  renderWithIntl(<ProgressBar label="Dönüştürülüyor…" />)
  expect(screen.queryByText(/uzun sürebilir/)).toBeNull()
  act(() => {
    vi.advanceTimersByTime(61_000)
  })
  expect(screen.getByText(/Yoğunluktan dolayı işleminiz normalden uzun sürebilir/)).toBeInTheDocument()
})
