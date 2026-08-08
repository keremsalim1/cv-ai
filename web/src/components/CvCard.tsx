import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { FileText, Eye, Target, Trash2, FileOutput } from 'lucide-react'
import type { CvRow } from '@/types/db'
import { PressableCard } from '@/components/motion/PressableCard'

export function CvCard({ cv, onDelete }: { cv: CvRow; onDelete?: () => void }) {
  const t = useTranslations('dashboard')
  return (
    <PressableCard className="flex items-center justify-between gap-4 rounded-xl bg-card p-4 text-card-foreground shadow-e1 ring-1 ring-foreground/[0.07] hover:shadow-e2">
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-primary/8 text-primary ring-1 ring-primary/12">
          <FileText aria-hidden className="size-5" />
        </span>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="type-ui truncate text-foreground">{cv.parsed_data.full_name}</span>
            {cv.is_ats && (
              <span className="rounded-full bg-success/12 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-success">
                {t('atsBadge')}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-1.5">
        <Link
          href={`/cv/${cv.id}`}
          className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          <Eye aria-hidden className="size-4" />
          {t('viewAction')}
        </Link>
        <Link
          href={`/score?cv=${cv.id}`}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary/8 px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:bg-primary/14"
        >
          <Target aria-hidden className="size-4" />
          {t('scoreAction')}
        </Link>
        <Link
          href={`/ats?cv=${cv.id}`}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary/8 px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:bg-primary/14"
        >
          <FileOutput aria-hidden className="size-4" />
          {t('atsAction')}
        </Link>
        {onDelete && (
          <button
            onClick={onDelete}
            aria-label={t('deleteAction')}
            title={t('deleteAction')}
            className="inline-flex items-center rounded-md p-2 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 aria-hidden className="size-4" />
          </button>
        )}
      </div>
    </PressableCard>
  )
}
