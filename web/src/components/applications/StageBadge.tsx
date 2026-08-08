'use client'
import { AnimatePresence, motion } from 'motion/react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'
import { flow } from '@/lib/motion'
import type { ApplicationStage } from '@/types/db'

const TONE: Record<ApplicationStage, string> = {
  received: 'bg-muted text-muted-foreground ring-border',
  in_review: 'bg-primary/8 text-primary ring-primary/15',
  interview: 'bg-amber-500/10 text-amber-700 ring-amber-500/20 dark:text-amber-400',
  offer: 'bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-400',
  rejected: 'bg-destructive/8 text-destructive ring-destructive/15',
}

/**
 * Keyed on the stage so a sync that moves an application crossfades the badge
 * instead of swapping the text underneath the user. This is the one animation
 * here that carries information rather than polish.
 */
export function StageBadge({ stage }: { stage: ApplicationStage }) {
  const t = useTranslations('applications.stage')
  return (
    <span className="relative inline-grid shrink-0">
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={stage}
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.94 }}
          transition={flow}
          className={cn(
            'rounded-full px-2.5 py-0.5 text-[11px] font-medium ring-1',
            TONE[stage]
          )}
        >
          {t(stage)}
        </motion.span>
      </AnimatePresence>
    </span>
  )
}
