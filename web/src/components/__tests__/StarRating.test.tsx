import { render, screen } from '@testing-library/react'
import { StarRating } from '@/components/StarRating'

it('renders filled and empty stars', () => {
  render(<StarRating stars={4} />)
  const el = screen.getByLabelText('4/5')
  expect(el).toHaveTextContent('★★★★☆')
})

it('renders one star minimum', () => {
  render(<StarRating stars={1} />)
  expect(screen.getByLabelText('1/5')).toHaveTextContent('★☆☆☆☆')
})
