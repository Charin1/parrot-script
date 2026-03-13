import { useEffect, useState } from 'react'
import { buildBackendUrl } from '../api/client'

export type BackendReachability = 'checking' | 'reachable' | 'unreachable'

interface HealthResponse {
  status?: string
  auth_required?: boolean
}

export function useLocalRuntime() {
  const [browserOnline, setBrowserOnline] = useState(() => window.navigator.onLine)
  const [backendReachability, setBackendReachability] = useState<BackendReachability>('checking')
  const [authRequired, setAuthRequired] = useState<boolean | null>(null)

  useEffect(() => {
    let cancelled = false
    let intervalId: number | null = null

    const checkBackend = async () => {
      const controller = new AbortController()
      const timeoutId = window.setTimeout(() => controller.abort(), 2500)

      setBackendReachability((current) => (current === 'reachable' ? current : 'checking'))

      try {
        const response = await fetch(buildBackendUrl('/health'), {
          signal: controller.signal,
          cache: 'no-store',
          headers: {
            'X-Requested-With': 'ParrotScriptClient',
          },
        })
        const payload = (await response.json().catch(() => ({}))) as HealthResponse
        const isHealthy = response.ok && payload.status === 'ok'

        if (!cancelled) {
          setBackendReachability(isHealthy ? 'reachable' : 'unreachable')
          setAuthRequired(isHealthy && typeof payload.auth_required === 'boolean' ? payload.auth_required : null)
        }
      } catch {
        if (!cancelled) {
          setBackendReachability('unreachable')
          setAuthRequired(null)
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

  return { browserOnline, backendReachability, authRequired }
}
