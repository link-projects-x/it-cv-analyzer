// Theme preference: "system" follows prefers-color-scheme; "light" / "dark" set data-theme on <html>.
// The choice is kept in localStorage for this browser only; storage errors are ignored.
export type ThemePref = 'system' | 'light' | 'dark'

const KEY = 'dou-cv-analyzer:theme'

export function readThemePref(): ThemePref {
  try {
    const v = typeof localStorage === 'undefined' ? null : localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

export function applyThemePref(pref: ThemePref, store = true): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  if (pref === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', pref)
  if (!store) return
  try {
    if (pref === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, pref)
  } catch {
    // private mode or blocked storage: the choice lasts until reload
  }
}

// Apply the stored choice as soon as the module loads, before the first render.
applyThemePref(readThemePref(), false)
