'use client'
import { MotionConfig } from 'motion/react'
import { flow } from '@/lib/motion'

/**
 * `reducedMotion="user"` is the whole accessibility story: Motion disables
 * transform and layout animations when the OS asks for reduced motion, and
 * keeps opacity. Doing this per-component would guarantee somewhere gets missed.
 */
export function MotionProvider({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user" transition={flow}>
      {children}
    </MotionConfig>
  )
}
