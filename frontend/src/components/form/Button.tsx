import type { ButtonHTMLAttributes } from 'react'

type ButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type'>

export function Button({ className, ...props }: ButtonProps) {
  return (
    <button
      type="button"
      className={`rounded-full bg-robin px-6 py-2 font-body text-lg text-parchment transition-colors hover:bg-robin/90 disabled:opacity-60 ${className ?? ''}`}
      {...props}
    />
  )
}
