import { screen } from '@testing-library/react'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'

const usePathname = vi.fn(() => '/dashboard')
vi.mock('next/navigation', () => ({ usePathname: () => usePathname() }))

import { AppSidebar } from '@/components/AppSidebar'

it('renders links for dashboard, score and ats', () => {
  renderWithIntl(<AppSidebar />)
  expect(screen.getByRole('link', { name: /Panel/ })).toHaveAttribute('href', '/dashboard')
  expect(screen.getByRole('link', { name: /Skorla/ })).toHaveAttribute('href', '/score')
  expect(screen.getByRole('link', { name: /ATS'ye Çevir/ })).toHaveAttribute('href', '/ats')
})

it('marks the active item with aria-current', () => {
  usePathname.mockReturnValue('/score')
  renderWithIntl(<AppSidebar />)
  expect(screen.getByRole('link', { name: /Skorla/ })).toHaveAttribute('aria-current', 'page')
  expect(screen.getByRole('link', { name: /Panel/ })).not.toHaveAttribute('aria-current')
})

it('shows optimize as disabled with a soon badge', () => {
  renderWithIntl(<AppSidebar />)
  expect(screen.queryByRole('link', { name: /Optimize/ })).toBeNull()
  expect(screen.getByText(/Optimize & Başvur/)).toBeInTheDocument()
  expect(screen.getByText(/yakında/)).toBeInTheDocument()
})
