import { useTranslation } from 'react-i18next'

interface StatusErrorProps {
  message: string
  detail?: string | null
}

/** A short error message with the full technical detail tucked behind a toggle. */
export function StatusError({ message, detail }: StatusErrorProps) {
  const { t } = useTranslation()
  return (
    <div>
      <p className="font-body text-robin">{message}</p>
      {detail !== null && detail !== undefined && detail !== '' ? (
        <details className="mt-1">
          <summary className="cursor-pointer font-body text-xs text-ink-soft hover:text-ink">
            {t('common.showDetails')}
          </summary>
          <pre className="mt-1 max-h-40 overflow-auto rounded-md border border-bark/20 bg-parchment-deep/50 p-2 font-mono text-xs break-words whitespace-pre-wrap text-ink-soft">
            {detail}
          </pre>
        </details>
      ) : null}
    </div>
  )
}
