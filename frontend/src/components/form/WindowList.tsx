import { useTranslation } from 'react-i18next'
import type { ActiveWindow } from '@/api/client'
import { controlClass } from '@/components/form/styles'

interface WindowListProps {
  windows: ActiveWindow[]
  onChange: (windows: ActiveWindow[]) => void
}

export function WindowList({ windows, onChange }: WindowListProps) {
  const { t } = useTranslation()

  function patch(index: number, change: Partial<ActiveWindow>) {
    onChange(windows.map((w, i) => (i === index ? { ...w, ...change } : w)))
  }

  return (
    <div className="flex flex-col gap-2">
      {windows.map((window, index) => (
        <div key={index} className="flex items-center gap-2">
          <input
            type="time"
            value={window.start}
            onChange={(e) => {
              patch(index, { start: e.target.value })
            }}
            className={controlClass}
          />
          <span className="font-body text-ink-soft">{t('schedule.to')}</span>
          <input
            type="time"
            value={window.end}
            onChange={(e) => {
              patch(index, { end: e.target.value })
            }}
            className={controlClass}
          />
          <button
            type="button"
            onClick={() => {
              onChange(windows.filter((_, i) => i !== index))
            }}
            className="font-body text-sm text-robin hover:underline"
          >
            {t('schedule.remove')}
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => {
          onChange([...windows, { start: '09:00', end: '17:00' }])
        }}
        className="self-start font-body text-sm text-ink-soft hover:text-ink hover:underline"
      >
        {t('schedule.addWindow')}
      </button>
    </div>
  )
}
