'use client'
import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Send, PackageOpen, Wand2 } from 'lucide-react'
import type { FieldAnswer, OptimizedPayload } from '@/types/api'
import { Button } from '@/components/ui/button'
import { FormAnswerField } from './FormAnswerField'

export function ApprovalScreen({ payload, canSubmit, onSubmit, onDeliver, onAssist }: {
  payload: OptimizedPayload
  canSubmit: boolean
  onSubmit: (answers: FieldAnswer[], coverLetter: string) => void
  onDeliver: (answers: FieldAnswer[], coverLetter: string) => void
  onAssist?: () => void
}) {
  const t = useTranslations('optimize')
  const [coverLetter, setCoverLetter] = useState(payload.cover_letter ?? '')
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(payload.answers.map((a) => [a.field_id, a.value]))
  )

  const answers = (): FieldAnswer[] =>
    payload.form
      .filter((f) => f.type !== 'file')
      .map((f) => ({ field_id: f.id, value: values[f.id] ?? '' }))

  return (
    <div className="flex flex-col gap-7">
      <section className="flex flex-col gap-3 rounded-2xl bg-card p-6 ring-1 ring-foreground/10">
        <h2 className="text-lg font-semibold text-foreground">{payload.cv.full_name}</h2>
        {payload.cv.summary && (
          <p className="text-[15px] leading-relaxed text-muted-foreground">{payload.cv.summary}</p>
        )}
        {payload.changes.length > 0 && (
          <div>
            <p className="mb-1 text-sm font-medium text-foreground">{t('changes')}</p>
            <ul className="list-disc pl-5 text-sm text-muted-foreground">
              {payload.changes.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          </div>
        )}
        {(payload.verification_required?.length ?? 0) > 0 && (
          <div data-testid="approval-verification">
            <p className="mb-1 text-sm font-medium text-foreground">{t('verification')}</p>
            <ul className="list-disc pl-5 text-sm text-muted-foreground">
              {payload.verification_required!.map((v, i) => <li key={i}>{v}</li>)}
            </ul>
          </div>
        )}
      </section>

      <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
        {t('coverLetter')}
        <textarea
          className="min-h-32 rounded-lg border border-border bg-background px-3 py-2 text-base text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          value={coverLetter} onChange={(e) => setCoverLetter(e.target.value)}
        />
      </label>

      {payload.form.length > 0 && (
        <section className="flex flex-col gap-4">
          <p className="text-sm font-medium text-foreground">{t('formAnswers')}</p>
          {payload.form.map((field) => (
            <FormAnswerField
              key={field.id} field={field} value={values[field.id] ?? ''}
              onChange={(v) => setValues((prev) => ({ ...prev, [field.id]: v }))}
            />
          ))}
        </section>
      )}

      <div className="flex flex-wrap gap-3">
        {canSubmit && (
          <Button onClick={() => onSubmit(answers(), coverLetter)} className="h-11 gap-1.5 text-base">
            <Send aria-hidden className="size-4" />
            {t('submit')}
          </Button>
        )}
        {onAssist && (
          <Button onClick={onAssist} className="h-11 gap-1.5 text-base">
            <Wand2 aria-hidden className="size-4" />
            {t('assistCta')}
          </Button>
        )}
        <Button variant="outline" onClick={() => onDeliver(answers(), coverLetter)} className="h-11 gap-1.5 text-base">
          <PackageOpen aria-hidden className="size-4" />
          {t('deliver')}
        </Button>
      </div>
    </div>
  )
}
