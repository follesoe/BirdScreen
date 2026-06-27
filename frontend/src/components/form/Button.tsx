import type { ButtonHTMLAttributes } from 'react'

type ButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type'>

export function Button({ className, ...props }: ButtonProps) {
  return (
    <button
      type="button"
      className={`rounded-full bg-robin px-6 py-2 font-body text-lg text-parchment shadow-[0_2px_4px_rgba(74,58,40,0.3)] transition-all hover:bg-robin/90 active:translate-y-px active:shadow-sm disabled:opacity-60 ${className ?? ''}`}
      {...props}
    />
  )
}
