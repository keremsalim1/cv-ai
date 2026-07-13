import { screen } from '@testing-library/react'
import { renderWithIntl } from '@/test/utils'
import Home from '@/app/page'

it('renders the pitch and a register CTA', () => {
  renderWithIntl(<Home />)
  expect(screen.getByRole('heading', { name: "CV'nizi yapay zeka ile işe hazırlayın" })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Ücretsiz Başla' })).toHaveAttribute('href', '/register')
})
