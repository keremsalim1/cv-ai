import Link from 'next/link'
import { useTranslations } from 'next-intl'
import type { CvRow } from '@/types/db'
import { Card } from '@/components/ui/card'

export function CvCard({ cv }: { cv: CvRow }) {
  const t = useTranslations('dashboard')
  return (
    <Card className="flex items-center justify-between p-4">
      <div className="flex items-center gap-2">
        <span className="font-medium">{cv.parsed_data.full_name}</span>
        {cv.is_ats && (
          <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs font-semibold text-emerald-800">
            {t('atsBadge')}
          </span>
        )}
      </div>
      <div className="flex gap-3 text-sm">
        <Link className="underline" href={`/cv/${cv.id}`}>{t('viewAction')}</Link>
        <Link className="underline" href={`/cv/${cv.id}/score`}>{t('scoreAction')}</Link>
      </div>
    </Card>
  )
}
