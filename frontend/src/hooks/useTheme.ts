import { useEffect, useMemo, useState } from 'react'

export type ThemeMode = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'parrot-script-theme-mode'

function readStoredMode(): ThemeMode {
  const saved = window.localStorage.getItem(STORAGE_KEY)
  if (saved === 'light' || saved === 'dark' || saved === 'system') {
    return saved
  }
  return 'system'
}

function resolveTheme(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'light' || mode === 'dark') {
    return mode
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(() => readStoredMode())
  const [resolved, setResolved] = useState<'light' | 'dark'>(() => resolveTheme(readStoredMode()))

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')

    const update = () => setResolved(resolveTheme(mode))
    update()

    const onChange = () => {
      if (mode === 'system') {
        update()
      }
    }

    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [mode])

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, mode)
    document.documentElement.setAttribute('data-theme', resolved)
  }, [mode, resolved])

  const value = useMemo(
    () => ({
      mode,
      resolved,
      setMode,
    }),
    [mode, resolved],
  )

  return value
}
