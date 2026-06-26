import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '@/api/client'

export function Logs() {
  const { t } = useTranslation()
  const [lines, setLines] = useState<string[]>([])

  const refresh = useCallback(() => {
    void api
      .logs()
      .then((res) => {
        setLines(res.lines)
      })
      .catch(() => {
        // logs are best-effort; ignore transient fetch errors
      })
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 3000)
    return () => {
      clearInterval(id)
    }
  }, [refresh])

  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-display text-3xl text-ink">{t('logs.heading')}</h2>
        <button
          type="button"
          onClick={refresh}
          className="rounded-full border border-bark/40 px-4 py-1 font-body text-ink-soft transition-colors hover:bg-parchment-deep"
        >
          {t('logs.refresh')}
        </button>
      </div>
      {lines.length === 0 ? (
        <p className="text-ink-soft">{t('logs.empty')}</p>
      ) : (
        <pre className="overflow-x-auto rounded-xl border border-bark/25 bg-parchment-deep p-4 font-mono text-xs leading-relaxed text-ink">
          {lines.join('\n')}
        </pre>
      )}
    </section>
  )
}
