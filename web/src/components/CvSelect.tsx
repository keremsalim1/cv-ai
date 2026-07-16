'use client'
import { useTranslations } from 'next-intl'
import type { CvRow } from '@/types/db'

export function CvSelect({ cvs, value, onChange }: {
  cvs: CvRow[]
  value: string
  onChange: (id: string) => void
}) {
  const t = useTranslations()
  return (
    <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
      {t('common.cvLabel')}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-11 rounded-lg border border-border bg-background px-3 text-base font-medium text-foreground transition-all outline-none hover:bg-muted focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        {cvs.map((c) => (
          <option key={c.id} value={c.id}>
            {c.parsed_data.full_name}
            {c.is_ats ? ' — ATS' : ''} ({new Date(c.created_at).toLocaleDateString()})
          </option>
        ))}
      </select>
    </label>
  )
}
