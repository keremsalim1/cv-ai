'use client'
import { useCallback, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { RefreshCw } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { createClient } from '@/lib/supabase/client'
import { listApplicationEvents, listApplications } from '@/lib/db'
import { inboxConnect, inboxStatus, inboxSync, type InboxStatus } from '@/lib/api'
import { GMAIL_REDIRECT_PATH, takeOAuthState } from '@/lib/gmailOAuth'
import { flow, snap } from '@/lib/motion'
import { Stagger, StaggerItem } from '@/components/motion/Stagger'
import type { ApplicationRow } from '@/types/db'
import { ApplicationCard } from '@/components/applications/ApplicationCard'
import { ConnectGmailCard } from '@/components/applications/ConnectGmailCard'

const STALE_MS = 15 * 60 * 1000

export default function ApplicationsPage() {
  const t = useTranslations('applications')
  const router = useRouter()
  const params = useSearchParams()
  const [supabase] = useState(createClient)
  const [rows, setRows] = useState<ApplicationRow[] | null>(null)
  const [status, setStatus] = useState<InboxStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const loadRows = useCallback(async () => {
    setRows(await listApplications(supabase))
  }, [supabase])

  const runSync = useCallback(async () => {
    setBusy(true)
    setNotice(null)
    try {
      const report = await inboxSync()
      if (report.partial) setNotice(t('partial'))
      setStatus(await inboxStatus())
      await loadRows()
    } catch {
      setNotice(t('revoked'))
    } finally {
      setBusy(false)
    }
  }, [loadRows, t])

  useEffect(() => {
    let cancelled = false
    async function boot() {
      const code = params.get('gmail_code')
      if (params.get('gmail') === 'denied') setNotice(t('denied'))
      if (code) {
        // Strip the code from the URL before anything else can re-trigger it.
        router.replace('/applications')
        // The state is single-use: read it before deciding anything, so a
        // replayed callback finds nothing waiting either way.
        const expected = takeOAuthState()
        const returned = params.get('gmail_state')
        if (!expected || expected !== returned) {
          // Someone else's code, or a flow this tab never started.
          setNotice(t('denied'))
        } else {
          try {
            await inboxConnect(code, window.location.origin + GMAIL_REDIRECT_PATH)
          } catch {
            setNotice(t('denied'))
          }
        }
      }
      const current = await inboxStatus()
      if (cancelled) return
      setStatus(current)
      await loadRows()
      const last = current.last_synced_at ? Date.parse(current.last_synced_at) : 0
      if (current.connected && current.status === 'active' && Date.now() - last > STALE_MS) {
        await runSync()
      }
    }
    boot()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadEvents = useCallback(
    (id: string) => listApplicationEvents(supabase, id), [supabase]
  )

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-10 px-5 py-16 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="type-title text-ink">{t('title')}</h1>
          {status?.connected && (
            <p className="type-meta mt-2 text-muted-foreground">
              {t('connected')} · {status.email} ·{' '}
              {status.last_synced_at
                ? t('syncedAt', { time: new Date(status.last_synced_at).toLocaleTimeString() })
                : t('neverSynced')}
            </p>
          )}
        </div>

        {status?.connected && (
          <motion.button
            type="button"
            onClick={runSync}
            disabled={busy}
            whileHover={busy ? undefined : { y: -2 }}
            whileTap={busy ? undefined : { scale: 0.98, transition: snap }}
            // The label swaps between two lengths; a floor stops the row jumping.
            className="type-ui inline-flex min-w-[13rem] items-center justify-center gap-2 rounded-lg px-4 py-2 text-foreground ring-1 ring-border hover:bg-accent disabled:opacity-60"
          >
            <RefreshCw aria-hidden className={`size-4 ${busy ? 'animate-spin' : ''}`} />
            {busy ? t('refreshing') : t('refresh')}
          </motion.button>
        )}
      </div>

      {status?.status === 'revoked' && (
        <p className="type-ui rounded-lg bg-destructive/8 px-4 py-3 text-destructive">
          {t('revoked')}
        </p>
      )}
      {notice && (
        <p className="type-ui rounded-lg bg-muted px-4 py-3 text-muted-foreground">{notice}</p>
      )}

      {status && !status.connected && <ConnectGmailCard />}

      {/* The skeleton fades out as the list staggers in, so the swap is a
          dissolve rather than a cut. `mode="wait"` holds the entrance until
          the placeholder has gone. */}
      <AnimatePresence mode="wait" initial={false}>
        {rows === null && (
          <motion.div
            key="skeleton"
            exit={{ opacity: 0 }}
            transition={flow}
            className="flex flex-col gap-3"
            aria-hidden
          >
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-[84px] animate-pulse rounded-xl bg-muted/70" />
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {rows === null ? null : rows.length === 0 ? (
        <p className="type-body text-muted-foreground">{t('empty')}</p>
      ) : (
        <Stagger as="ul" className="flex flex-col gap-3">
          {rows.map((row, i) => (
            <StaggerItem as="li" key={row.id} index={i}>
              <ApplicationCard row={row} loadEvents={loadEvents} />
            </StaggerItem>
          ))}
        </Stagger>
      )}
    </main>
  )
}
