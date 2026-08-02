import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { MotionProvider } from '@/components/motion/MotionProvider'
import {
  flow, settle, snap, staggerDelay, STAGGER_MAX_ITEMS, STAGGER_STEP,
} from '@/lib/motion'

it('renders its children', () => {
  render(<MotionProvider><p>hello</p></MotionProvider>)
  expect(screen.getByText('hello')).toBeInTheDocument()
})

it('every speed is one spring family, fastest to slowest', () => {
  for (const t of [snap, flow, settle]) {
    expect(t.type).toBe('spring')
    expect(t.bounce).toBeLessThanOrEqual(0.25)
  }
  // A press must outrun a hover, and a hover must outrun a height change,
  // or the interface feels like three different products.
  expect(snap.visualDuration).toBeLessThan(flow.visualDuration as number)
  expect(flow.visualDuration).toBeLessThan(settle.visualDuration as number)
})

it('staggers inside the perceptible band', () => {
  // Below 30ms a stagger reads as a single event; above 50ms it reads as a queue.
  expect(STAGGER_STEP).toBeGreaterThanOrEqual(0.03)
  expect(STAGGER_STEP).toBeLessThanOrEqual(0.05)
})

it('caps the entrance so a long list never becomes a queue', () => {
  // A user with 200 applications must not wait 7 seconds for the last row.
  expect(staggerDelay(200)).toBeLessThanOrEqual(0.5)
})

it('staggers the head of the list and lands the tail together', () => {
  expect(staggerDelay(0)).toBe(0)
  expect(staggerDelay(3)).toBeCloseTo(3 * STAGGER_STEP)
  // Past the cap the delay stops growing — that is the whole point.
  expect(staggerDelay(STAGGER_MAX_ITEMS)).toBe(staggerDelay(1000))
})
