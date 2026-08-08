'use client'
import { motion, type Variants } from 'motion/react'
import { flow, staggerDelay } from '@/lib/motion'

const container: Variants = { hidden: {}, show: {} }

/**
 * The delay is computed per index rather than handed to `stagger()`, because
 * `stagger()` keeps multiplying forever: a 200-row list would take seven
 * seconds to finish arriving. Past the cap every remaining row shares the last
 * delay, so a long list still has a rhythm but never a queue.
 */
const item: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: (index: number) => ({
    opacity: 1,
    y: 0,
    transition: { ...flow, delay: staggerDelay(index) },
  }),
}

export function Stagger({ children, className, as = 'div' }: {
  children: React.ReactNode
  className?: string
  as?: 'div' | 'ul'
}) {
  const Tag = as === 'ul' ? motion.ul : motion.div
  return (
    <Tag variants={container} initial="hidden" animate="show" className={className}>
      {children}
    </Tag>
  )
}

export function StaggerItem({ children, className, index = 0, as = 'div' }: {
  children: React.ReactNode
  className?: string
  /** Position in the list. Drives the capped delay; pass the map index. */
  index?: number
  as?: 'div' | 'li'
}) {
  const Tag = as === 'li' ? motion.li : motion.div
  return (
    <Tag variants={item} custom={index} className={className}>
      {children}
    </Tag>
  )
}
