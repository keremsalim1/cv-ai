'use client'
import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import type { SupabaseClient } from '@supabase/supabase-js'
import { listApplications } from '@/lib/db'
import type { ApplicationRow } from '@/types/db'

// 'external' (email-discovered, never submitted by us) has no translation key yet;
// it isn't produced anywhere in Task 1, and display is out of scope for this task.
const STATUS_KEY: Partial<Record<ApplicationRow['status'], string>> = {
  submitted: 'statusSubmitted', delivered: 'statusDelivered', failed: 'statusFailed',
}

export function RecentApplications({ supabase }: { supabase: SupabaseClient }) {
  const t = useTranslations('optimize')
  const [rows, setRows] = useState<ApplicationRow[] | null>(null)

  useEffect(() => {
    listApplications(supabase).then(setRows).catch(() => setRows([]))
  }, [supabase])

  if (!rows || rows.length === 0) {
    return (
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-medium text-foreground">{t('recent')}</h2>
        <p className="text-sm text-muted-foreground">{rows ? t('recentEmpty') : '…'}</p>
      </section>
    )
  }

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-medium text-foreground">{t('recent')}</h2>
      <ul className="flex flex-col divide-y divide-border rounded-xl ring-1 ring-foreground/10">
        {rows.map((r) => {
          const statusKey = STATUS_KEY[r.status]
          return (
            <li key={r.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
              <span className="truncate text-muted-foreground">{r.url}</span>
              <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[11px] text-foreground">
                {statusKey ? t(statusKey) : r.status}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
