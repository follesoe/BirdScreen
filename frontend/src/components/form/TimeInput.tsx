import { controlClass } from '@/components/form/styles'

interface TimeInputProps {
  value: string
  onChange: (value: string) => void
}

/** Force HH:MM digits → "HH:MM"; e.g. typing 0600 becomes 06:00. */
function formatTime(raw: string): string {
  const digits = raw.replace(/\D/g, '').slice(0, 4)
  if (digits.length <= 2) {
    return digits
  }
  return `${digits.slice(0, 2)}:${digits.slice(2)}`
}

/**
 * A 24-hour HH:MM time field. We avoid the native `<input type="time">` because
 * it follows the OS locale and shows AM/PM there; this is always 24h.
 */
export function TimeInput({ value, onChange }: TimeInputProps) {
  return (
    <input
      type="text"
      inputMode="numeric"
      placeholder="06:00"
      maxLength={5}
      value={value}
      onChange={(e) => {
        onChange(formatTime(e.target.value))
      }}
      className={`${controlClass} w-24 text-center tabular-nums`}
    />
  )
}
