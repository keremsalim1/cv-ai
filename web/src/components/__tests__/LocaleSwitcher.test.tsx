import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import { LocaleSwitcher } from '@/components/LocaleSwitcher'

const refresh = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh }),
}))

it('shows the other locale and sets the cookie on click', async () => {
  renderWithIntl(<LocaleSwitcher />)
  const btn = screen.getByRole('button', { name: 'switch language' })
  expect(btn).toHaveTextContent('EN')
  await userEvent.click(btn)
  expect(document.cookie).toContain('locale=en')
  expect(refresh).toHaveBeenCalled()
})
