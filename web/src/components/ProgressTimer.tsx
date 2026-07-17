'use client'
import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'

/** Indeterminate progress bar with an elapsed-seconds counter, shown while
 *  an LLM-backed operation (scoring, ATS conversion) is in flight. */
export function ProgressTimer({ label }: { label: string }) {
  const t = useTranslations('common')
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="flex flex-col gap-1.5" role="status" aria-live="polite">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className="h-full w-1/3 rounded-full bg-primary motion-safe:animate-[progress-slide_1.4s_ease-in-out_infinite]" />
      </div>
      <p className="flex items-baseline justify-between font-mono text-xs tracking-wide text-muted-foreground">
        <span>{label}</span>
        <span>{t('elapsed', { seconds })}</span>
      </p>
    </div>
  )
}
