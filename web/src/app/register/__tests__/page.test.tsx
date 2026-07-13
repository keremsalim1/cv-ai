import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}))

const signUp = vi.fn(async () => ({ error: null }))
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({ auth: { signUp, signInWithOAuth: vi.fn(async () => ({ error: null })) } }),
}))

import RegisterPage from '@/app/register/page'

it('signs up with full name metadata and shows confirmation notice', async () => {
  renderWithIntl(<RegisterPage />)
  await userEvent.type(screen.getByLabelText('Ad Soyad'), 'Ada Lovelace')
  await userEvent.type(screen.getByLabelText('E-posta'), 'a@b.co')
  await userEvent.type(screen.getByLabelText('Şifre'), 'secret123')
  await userEvent.click(screen.getByRole('button', { name: 'Kayıt Ol' }))
  expect(signUp).toHaveBeenCalledWith(expect.objectContaining({
    email: 'a@b.co',
    password: 'secret123',
    options: expect.objectContaining({ data: { full_name: 'Ada Lovelace' } }),
  }))
  expect(await screen.findByText('Doğrulama bağlantısı için e-postanızı kontrol edin.')).toBeInTheDocument()
})
