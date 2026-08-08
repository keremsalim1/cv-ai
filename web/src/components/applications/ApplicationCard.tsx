'use client'
import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Disclosure } from '@/components/motion/Disclosure'
import { PressableCard } from '@/components/motion/PressableCard'
import type { ApplicationEventRow, ApplicationRow } from '@/types/db'
import { StageBadge } from './StageBadge'

export function ApplicationCard({ row, loadEvents, mailboxConnected }: {
  row: ApplicationRow
  loadEvents: (id: string) => Promise<ApplicationEventRow[]>
  // Without a mailbox there is no watch to report on, and saying "no email
  // yet" would promise one that is not running.
  mailboxConnected: boolean
}) {
  const t = useTranslations('applications')
  const [events, setEvents] = useState<ApplicationEventRow[] | null>(null)
  const [open, setOpen] = useState(false)

  async function toggle() {
    setOpen((was) => !was)
    if (events === null) setEvents(await loadEvents(row.id))
  }

  return (
    <PressableCard className="flex flex-col gap-3 rounded-xl bg-card px-4 py-4 shadow-e1 ring-1 ring-foreground/[0.07] hover:shadow-e2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="type-ui truncate text-foreground">
            {row.company ?? t('unknownCompany')}
          </p>
          {row.title && (
            <p className="type-meta truncate text-muted-foreground">{row.title}</p>
          )}
        </div>
        <StageBadge stage={row.stage} />
      </div>

      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="type-meta self-start text-primary hover:underline"
      >
        {t('why')}
      </button>

      <Disclosure open={open}>
        <div className="flex flex-col gap-2 rounded-lg bg-muted/50 px-3 py-2.5">
          {events === null ? (
            <span className="type-meta text-muted-foreground">…</span>
          ) : events.length === 0 ? (
            <span className="type-meta text-muted-foreground">
              {mailboxConnected ? t('noEvents') : t('noMailbox')}
            </span>
          ) : (
            events.map((e) => (
              <div key={e.id} className="flex flex-col gap-0.5">
                <span className="type-meta font-medium text-foreground">{e.subject}</span>
                <span className="type-meta text-muted-foreground">
                  {t('eventFrom')}: {e.from_address}
                  {e.received_at && ` · ${new Date(e.received_at).toLocaleDateString()}`}
                </span>
                {e.evidence && (
                  <span className="type-meta italic text-muted-foreground">
                    “{e.evidence}”
                  </span>
                )}
              </div>
            ))
          )}
        </div>
      </Disclosure>
    </PressableCard>
  )
}
