import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'

const push = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}))

const signInWithPassword = vi.fn(async () => ({ error: null }))
const signInWithOAuth = vi.fn(async () => ({ error: null }))
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({ auth: { signInWithPassword, signInWithOAuth } }),
}))

import LoginPage from '@/app/login/page'

it('logs in with email and password then routes to dashboard', async () => {
  renderWithIntl(<LoginPage />)
  await userEvent.type(screen.getByLabelText('E-posta'), 'a@b.co')
  await userEvent.type(screen.getByLabelText('Şifre'), 'secret123')
  await userEvent.click(screen.getByRole('button', { name: 'Giriş Yap' }))
  expect(signInWithPassword).toHaveBeenCalledWith({ email: 'a@b.co', password: 'secret123' })
  expect(push).toHaveBeenCalledWith('/dashboard')
})

it('starts Google OAuth', async () => {
  renderWithIntl(<LoginPage />)
  await userEvent.click(screen.getByRole('button', { name: 'Google ile devam et' }))
  expect(signInWithOAuth).toHaveBeenCalledWith(
    expect.objectContaining({ provider: 'google' })
  )
})
