'use client'
import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Download, Copy, CheckCircle2 } from 'lucide-react'
import type { FieldAnswer } from '@/types/api'
import { downloadBlob } from '@/lib/download'
import { Button } from '@/components/ui/button'

export function ResultScreen({ mode, screenshot, pdf, pdfName, coverLetter, answers }: {
  mode: 'submitted' | 'delivered'
  screenshot?: string
  pdf: Blob
  pdfName: string
  coverLetter: string
  answers: FieldAnswer[]
}) {
  const t = useTranslations('optimize')
  const [copied, setCopied] = useState<string | null>(null)

  const copy = async (key: string, text: string) => {
    await navigator.clipboard.writeText(text)
    setCopied(key)
    setTimeout(() => setCopied((c) => (c === key ? null : c)), 2000)
  }
  const answersText = answers.map((a) => `${a.field_id}: ${a.value}`).join('\n')

  return (
    <div className="flex flex-col gap-6">
      <p className="flex items-center gap-2 rounded-lg bg-success/10 px-4 py-3 text-sm text-success">
        <CheckCircle2 aria-hidden className="size-4 shrink-0" />
        {mode === 'submitted' ? t('resultSubmitted') : t('resultDelivered')}
      </p>

      {mode === 'submitted' && screenshot && (
        <img src={`data:image/png;base64,${screenshot}`} alt={t('resultSubmitted')}
          className="w-full rounded-xl border border-border" />
      )}

      <div className="flex flex-wrap gap-3">
        <Button onClick={() => downloadBlob(pdf, pdfName)} className="h-11 gap-1.5 text-base">
          <Download aria-hidden className="size-4" />
          {t('downloadPdf')}
        </Button>
        <Button variant="outline" onClick={() => copy('cover', coverLetter)} className="h-11 gap-1.5 text-base">
          <Copy aria-hidden className="size-4" />
          {copied === 'cover' ? t('copied') : t('copyCoverLetter')}
        </Button>
        {answers.length > 0 && (
          <Button variant="outline" onClick={() => copy('answers', answersText)} className="h-11 gap-1.5 text-base">
            <Copy aria-hidden className="size-4" />
            {copied === 'answers' ? t('copied') : t('copyAnswers')}
          </Button>
        )}
      </div>
    </div>
  )
}
