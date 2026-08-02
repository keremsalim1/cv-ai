'use client'
import { motion } from 'motion/react'
import { flow, snap } from '@/lib/motion'

/**
 * Hover lifts, press compresses. Both are transform-only, which is what lets
 * the reduced-motion policy switch them off cleanly.
 */
export function PressableCard({ children, className, as = 'div' }: {
  children: React.ReactNode
  className?: string
  as?: 'div' | 'li'
}) {
  const Tag = as === 'li' ? motion.li : motion.div
  return (
    <Tag
      className={className}
      whileHover={{ y: -2 }}
      whileTap={{ scale: 0.985, transition: snap }}
      transition={flow}
    >
      {children}
    </Tag>
  )
}
