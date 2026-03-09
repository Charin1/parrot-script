import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

const stored = window.localStorage.getItem('parrot-script-theme-mode')
const mode = stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system'
const resolved =
  mode === 'system'
    ? window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light'
    : mode
document.documentElement.setAttribute('data-theme', resolved)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
