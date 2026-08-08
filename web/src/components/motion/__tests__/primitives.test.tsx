import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { Disclosure } from '@/components/motion/Disclosure'
import { PressableCard } from '@/components/motion/PressableCard'
import { Stagger, StaggerItem } from '@/components/motion/Stagger'

it('a stagger renders a real list when asked for one', () => {
  render(
    <Stagger as="ul" className="grid">
      <StaggerItem as="li" index={0}>first</StaggerItem>
      <StaggerItem as="li" index={1}>second</StaggerItem>
    </Stagger>
  )
  // Motion must not cost us the semantics: a list has to stay a list.
  expect(screen.getByRole('list')).toBeInTheDocument()
  expect(screen.getAllByRole('listitem')).toHaveLength(2)
})

it('a pressable card keeps its content addressable', () => {
  render(<PressableCard className="card">clickable content</PressableCard>)
  expect(screen.getByText('clickable content')).toBeInTheDocument()
})

it('a closed disclosure exposes nothing to assistive technology', () => {
  render(<Disclosure open={false}><p>the evidence</p></Disclosure>)
  expect(screen.queryByText('the evidence')).not.toBeInTheDocument()
})

it('an open disclosure exposes its content immediately, not after animating', () => {
  render(<Disclosure open><p>the evidence</p></Disclosure>)
  expect(screen.getByText('the evidence')).toBeInTheDocument()
})
