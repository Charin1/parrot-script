import { useEffect, useState } from 'react'

export type BackendReachability = 'checking' | 'reachable' | 'unreachable'

export function useLocalRuntime() {
  const [browserOnline, setBrowserOnline] = useState(() => window.navigator.onLine)
  const [backendReachability, setBackendReachability] = useState<BackendReachability>('checking')

  useEffect(() => {
    let cancelled = false
    let intervalId: number | null = null

    const checkBackend = async () => {
      const controller = new AbortController()
      const timeoutId = window.setTimeout(() => controller.abort(), 2500)

      setBackendReachability((current) => (current === 'reachable' ? current : 'checking'))

      try {
        const response = await fetch('/health', {
          signal: controller.signal,
          cache: 'no-store',
          headers: {
            'X-Requested-With': 'ParrotScriptClient',
          },
        })

        if (!cancelled) {
          setBackendReachability(response.ok ? 'reachable' : 'unreachable')
        }
      } catch {
        if (!cancelled) {
          setBackendReachability('unreachable')
        }
      } finally {
        window.clearTimeout(timeoutId)
      }
    }

    const handleOnline = () => {
      setBrowserOnline(true)
      void checkBackend()
    }

    const handleOffline = () => {
      setBrowserOnline(false)
      void checkBackend()
    }

    void checkBackend()
    intervalId = window.setInterval(() => {
      void checkBackend()
    }, 15000)

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      cancelled = true
      if (intervalId !== null) {
        window.clearInterval(intervalId)
      }
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  return { browserOnline, backendReachability }
}
