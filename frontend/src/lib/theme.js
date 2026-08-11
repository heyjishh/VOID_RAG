import { useEffect, useState } from 'react'

const STORAGE_KEY = 'juryai.theme'

export function getStoredTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored === 'dark' || stored === 'light' ? stored : 'system'
  } catch {
    return 'system'
  }
}

function applyTheme(theme) {
  const root = document.documentElement
  if (theme === 'dark' || theme === 'light') root.setAttribute('data-theme', theme)
  else root.removeAttribute('data-theme')
}

export function persistTheme(theme) {
  try {
    if (theme === 'system') localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // Storage unavailable (private mode, quota) — theme still applies for this tab.
  }
  applyTheme(theme)
}

export function useTheme() {
  const [theme, setThemeState] = useState(getStoredTheme)

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  function setTheme(next) {
    persistTheme(next)
    setThemeState(next)
  }

  return [theme, setTheme]
}
