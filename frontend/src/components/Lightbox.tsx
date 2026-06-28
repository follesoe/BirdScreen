import { useEffect, useRef, useState, type TouchEvent } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { api, type GenerationLogEntry } from '@/api/client'
import frameUrl from '@/assets/frame.webp'

interface LightboxProps {
  name: string
  record: GenerationLogEntry | undefined
  onClose: () => void
  onPrev?: (() => void) | undefined
  onNext?: (() => void) | undefined
}

function fmt(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

const PILL = 'rounded-full bg-paper/90 px-4 py-1.5 font-body text-sm text-ink shadow hover:bg-paper'
const PRIMARY =
  'rounded-full bg-robin px-4 py-1.5 font-body text-sm text-parchment shadow hover:bg-robin/90 disabled:opacity-60'
const DARK =
  'rounded-full bg-ink px-4 py-1.5 font-body text-sm text-parchment shadow hover:bg-ink/90'

export function Lightbox({ name, record, onClose, onPrev, onNext }: LightboxProps) {
  const { t } = useTranslation()
  const [showInfo, setShowInfo] = useState(false)
  const [showPrompt, setShowPrompt] = useState(false)
  const [hanging, setHanging] = useState(false)
  const [sendMessage, setSendMessage] = useState<string | null>(null)
  const touchStartX = useRef<number | null>(null)

  const onTouchStart = (e: TouchEvent<HTMLDivElement>) => {
    touchStartX.current = e.touches[0]?.clientX ?? null
  }
  const onTouchEnd = (e: TouchEvent<HTMLDivElement>) => {
    const start = touchStartX.current
    touchStartX.current = null
    if (start === null) return
    const dx = (e.changedTouches[0]?.clientX ?? start) - start
    if (Math.abs(dx) < 50) return // ignore taps/tiny drags
    if (dx < 0) onNext?.()
    else onPrev?.()
  }
  const promptText = record?.prompt ?? null

  const hang = () => {
    setHanging(true)
    setSendMessage(null)
    void api
      .sendToTv(name)
      .then((r) => {
        setSendMessage(r.message)
      })
      .catch((e: unknown) => {
        setSendMessage(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        setHanging(false)
      })
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showPrompt) setShowPrompt(false)
        else onClose()
      } else if (!showPrompt && e.key === 'ArrowLeft') {
        onPrev?.()
      } else if (!showPrompt && e.key === 'ArrowRight') {
        onNext?.()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [onClose, onPrev, onNext, showPrompt])

  const rows: [string, string | null][] = record
    ? [
        [t('gallery.infoTime'), fmt(record.created_at)],
        [t('gallery.infoLocation'), record.location],
        [t('gallery.infoWeather'), record.weather],
        [t('gallery.infoSeason'), record.season],
        [t('gallery.infoModel'), record.model],
        [t('gallery.infoBirds'), record.birds.join(', ') || null],
        [
          t('gallery.infoTokens'),
          record.total_tokens !== null ? record.total_tokens.toLocaleString() : null,
        ],
        [t('gallery.infoCost'), record.cost_usd !== null ? `$${record.cost_usd.toFixed(4)}` : null],
      ]
    : []

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
      <button
        type="button"
        aria-label={t('gallery.close')}
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-black/70 backdrop-blur-sm"
      />
      <div
        className="relative z-10 flex flex-col"
        style={{ width: 'min(76rem, calc(78vh * 16 / 9))' }}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
        <div className="mb-3 flex items-center gap-2">
          {sendMessage !== null ? (
            <span className="mr-auto truncate rounded-full bg-paper/90 px-3 py-1 font-body text-sm text-ink shadow">
              {sendMessage}
            </span>
          ) : (
            <span className="mr-auto" />
          )}
          <button
            type="button"
            onClick={() => {
              setShowInfo((v) => !v)
            }}
            className={PILL}
          >
            {t('gallery.info')}
          </button>
          {promptText !== null ? (
            <button
              type="button"
              onClick={() => {
                setShowPrompt(true)
              }}
              className={PILL}
            >
              {t('gallery.prompt')}
            </button>
          ) : null}
          <button type="button" onClick={hang} disabled={hanging} className={PRIMARY}>
            {hanging ? t('gallery.hanging') : t('gallery.hang')}
          </button>
          <button type="button" onClick={onClose} className={DARK}>
            {t('gallery.close')}
          </button>
        </div>

        <div className="relative w-full">
          {/* the wood is a CSS border-image, so the poster shows full 16:9 (no crop) */}
          <img
            src={api.imageUrl(name)}
            alt={name}
            className="block w-full select-none shadow-2xl"
            style={{
              aspectRatio: '16 / 9',
              objectFit: 'cover',
              borderStyle: 'solid',
              borderWidth: 'clamp(12px, 1.8vw, 24px)',
              borderImageSource: `url(${frameUrl})`,
              borderImageSlice: '47 48 47 49',
              borderImageRepeat: 'stretch',
            }}
          />

          {showInfo ? (
            <div className="absolute bottom-6 left-6 max-h-[78%] w-72 overflow-y-auto rounded-lg border border-bark/30 bg-paper/95 p-4 text-sm shadow-lg">
              {record ? (
                <dl>
                  {rows.map(([label, value]) =>
                    value !== null ? (
                      <div
                        key={label}
                        className="flex justify-between gap-4 border-b border-bark/15 py-1.5 last:border-0"
                      >
                        <dt className="font-body text-ink-soft">{label}</dt>
                        <dd className="text-right font-body text-ink">{value}</dd>
                      </div>
                    ) : null,
                  )}
                </dl>
              ) : (
                <p className="font-body text-ink-soft">{t('gallery.noMetadata')}</p>
              )}
            </div>
          ) : null}
        </div>
      </div>

      {showPrompt && promptText !== null ? (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-6">
          <button
            type="button"
            aria-label={t('gallery.close')}
            onClick={() => {
              setShowPrompt(false)
            }}
            className="absolute inset-0 cursor-default bg-black/60"
          />
          <div className="relative z-10 max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-bark/30 bg-paper p-5 shadow-lg">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-display text-xl text-ink">{t('gallery.promptTitle')}</h3>
              <button
                type="button"
                onClick={() => {
                  setShowPrompt(false)
                }}
                className={PRIMARY}
              >
                {t('gallery.close')}
              </button>
            </div>
            <pre className="font-mono text-xs whitespace-pre-wrap text-ink">{promptText}</pre>
          </div>
        </div>
      ) : null}
    </div>,
    document.body,
  )
}
