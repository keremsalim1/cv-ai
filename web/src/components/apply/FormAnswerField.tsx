'use client'
import { useTranslations } from 'next-intl'
import type { FormField } from '@/types/api'

const SELECT_CLS =
  'h-11 rounded-lg border border-border bg-background px-3 text-base font-medium text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50'
const TEXT_CLS =
  'min-h-11 rounded-lg border border-border bg-background px-3 py-2 text-base text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50'

export function FormAnswerField({ field, value, onChange }: {
  field: FormField
  value: string
  onChange: (value: string) => void
}) {
  const t = useTranslations('optimize')
  const showRequired = field.required && !value.trim() && field.type !== 'file'

  return (
    <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
      <span className="flex items-center gap-2">
        {field.label}
        {showRequired && (
          <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-normal text-destructive">
            {t('requiredEmpty')}
          </span>
        )}
      </span>

      {field.type === 'file' ? (
        <span className="text-[13px] font-normal text-muted-foreground">{t('fileNote')}</span>
      ) : field.type === 'select' || field.type === 'radio' ? (
        <select className={SELECT_CLS} value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">—</option>
          {field.options.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      ) : field.type === 'checkbox' ? (
        <input
          type="checkbox"
          className="size-5 self-start accent-primary"
          checked={['yes', 'true', 'on', 'evet', '1'].includes(value.toLowerCase())}
          onChange={(e) => onChange(e.target.checked ? 'yes' : 'no')}
        />
      ) : (
        <textarea className={TEXT_CLS} rows={field.type === 'textarea' ? 4 : 1}
          value={value} onChange={(e) => onChange(e.target.value)} />
      )}
    </label>
  )
}
