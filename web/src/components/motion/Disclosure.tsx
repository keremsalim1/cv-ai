'use client'
import { AnimatePresence, motion } from 'motion/react'
import { settle } from '@/lib/motion'

/**
 * The one place we animate a non-transform property. A disclosure that scales
 * instead of growing distorts its own text, and one that snaps open loses the
 * connection between the button and what it revealed. Motion animates to
 * `height: "auto"` by measuring, so no layout projection is involved.
 */
export function Disclosure({ open, children, className }: {
  open: boolean
  children: React.ReactNode
  className?: string
}) {
  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          key="panel"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={settle}
          style={{ overflow: 'hidden' }}
          className={className}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
