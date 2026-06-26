interface ToggleProps {
  checked: boolean
  label: string
  onChange: (value: boolean) => void
}

export function Toggle({ checked, label, onChange }: ToggleProps) {
  return (
    <label className="flex items-center gap-3">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => {
          onChange(e.target.checked)
        }}
        className="h-5 w-5 accent-robin"
      />
      <span className="font-body text-ink">{label}</span>
    </label>
  )
}
