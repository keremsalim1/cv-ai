import { render } from '@testing-library/react'
import { expect, it, vi } from 'vitest'

const seen: Record<string, unknown> = {}
vi.mock('motion/react', () => ({
  MotionConfig: (props: Record<string, unknown>) => {
    Object.assign(seen, props)
    return <>{props.children as React.ReactNode}</>
  },
}))

it('defers to the operating system on reduced motion', async () => {
  // The single most important accessibility decision in this refresh, and the
  // only one a component could silently opt out of. Motion's default is
  // "never" — landing on that by accident would ship motion to people who
  // asked for none.
  const { MotionProvider } = await import('@/components/motion/MotionProvider')
  render(<MotionProvider><p>x</p></MotionProvider>)
  expect(seen.reducedMotion).toBe('user')
})
