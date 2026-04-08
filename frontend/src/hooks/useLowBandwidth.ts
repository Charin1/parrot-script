import { useCallback, useEffect, useState } from 'react'

const LOW_BANDWIDTH_KEY = 'parrot-low-bandwidth-mode'

/** Detects a slow network connection via the Network Information API if available. */
function detectSlowNetwork(): boolean {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const conn = (navigator as any).connection
  if (!conn) return false
  const slowTypes = ['slow-2g', '2g', '3g']
  if (slowTypes.includes(conn.effectiveType)) return true
  if (typeof conn.downlink === 'number' && conn.downlink < 1.5) return true
  return false
}

export function useLowBandwidth() {
  const [lowBandwidth, setLowBandwidth] = useState<boolean>(() => {
    const stored = localStorage.getItem(LOW_BANDWIDTH_KEY)
    if (stored !== null) return stored === 'true'
    return detectSlowNetwork()
  })

  // Auto-detect network changes
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const conn = (navigator as any).connection
    if (!conn) return
    const onChange = () => {
      // Only auto-downgrade, never auto-upgrade — the user must opt out manually
      if (detectSlowNetwork() && !lowBandwidth) {
        setLowBandwidth(true)
        localStorage.setItem(LOW_BANDWIDTH_KEY, 'true')
      }
    }
    conn.addEventListener('change', onChange)
    return () => conn.removeEventListener('change', onChange)
  }, [lowBandwidth])

  const toggleLowBandwidth = useCallback(() => {
    setLowBandwidth(prev => {
      const next = !prev
      localStorage.setItem(LOW_BANDWIDTH_KEY, String(next))
      return next
    })
  }, [])

  return { lowBandwidth, toggleLowBandwidth }
}
