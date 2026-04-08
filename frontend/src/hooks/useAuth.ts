import { useCallback, useState } from 'react'
import { clearApiToken, getApiToken, setApiToken } from '../api/client'
import { useLocalRuntime } from './useLocalRuntime'

export function useAuth() {
  const { browserOnline, backendReachability, authRequired } = useLocalRuntime()

  const [apiTokenInput, setApiTokenInput] = useState(() => getApiToken())
  const [activeApiToken, setActiveApiToken] = useState(() => getApiToken())

  const hasApiToken = activeApiToken.trim().length > 0
  const authReady = authRequired === false || hasApiToken

  const authBadgeClass =
    authRequired === null ? 'badge-idle' : authReady ? 'badge-ok' : 'badge-failed'
  const authBadgeLabel =
    authRequired === null
      ? 'Checking Auth'
      : authRequired
        ? hasApiToken
          ? 'Token Loaded'
          : 'Token Required'
        : 'Token Optional'
  const authDescription =
    authRequired === false
      ? 'Backend auth is disabled right now. You can leave the token blank unless you enable API_TOKEN again.'
      : 'The local API expects a shared token. It stays in this browser and is attached to API and live stream requests.'

  const saveApiToken = useCallback((token: string) => {
    const cleanToken = token.trim()
    if (!cleanToken) {
      clearApiToken()
      setApiTokenInput('')
      setActiveApiToken('')
      return false
    }

    setApiToken(cleanToken)
    setApiTokenInput(cleanToken)
    setActiveApiToken(cleanToken)
    return true
  }, [])

  const removeApiToken = useCallback(() => {
    clearApiToken()
    setApiTokenInput('')
    setActiveApiToken('')
  }, [])

  return {
    browserOnline,
    backendReachability,
    authRequired,
    authReady,
    apiTokenInput,
    setApiTokenInput,
    activeApiToken,
    authBadgeClass,
    authBadgeLabel,
    authDescription,
    saveApiToken,
    removeApiToken,
  }
}
