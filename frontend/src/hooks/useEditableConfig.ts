import { useCallback, useEffect, useState } from 'react'

export type SaveStatus = 'idle' | 'saving' | 'saved'

interface EditableConfig<T> {
  config: T | null
  status: SaveStatus
  update: <K extends keyof T>(key: K, value: T[K]) => void
  save: (current: T) => void
}

/**
 * Load a config section from the API, edit it locally, and save it back.
 * Shared by every settings screen so the load/edit/save behaviour is identical.
 * Pass stable `load`/`persist` references (e.g. the `api.*` methods).
 */
export function useEditableConfig<T extends object>(
  load: () => Promise<T>,
  persist: (value: T) => Promise<T>,
): EditableConfig<T> {
  const [config, setConfig] = useState<T | null>(null)
  const [status, setStatus] = useState<SaveStatus>('idle')

  useEffect(() => {
    let active = true
    void load()
      .then((loaded) => {
        if (active) setConfig(loaded)
      })
      .catch(() => {
        // leave config null → caller shows a loading state
      })
    return () => {
      active = false
    }
  }, [load])

  const update = useCallback(<K extends keyof T>(key: K, value: T[K]) => {
    setConfig((prev) => (prev === null ? prev : { ...prev, [key]: value }))
    setStatus('idle')
  }, [])

  const save = useCallback(
    (current: T) => {
      setStatus('saving')
      void persist(current)
        .then((saved) => {
          setConfig(saved)
          setStatus('saved')
        })
        .catch(() => {
          setStatus('idle')
        })
    },
    [persist],
  )

  return { config, status, update, save }
}
