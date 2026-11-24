import { useState } from 'react'
import { applyThemePref, readThemePref, type ThemePref } from '../theme'

const OPTIONS: { value: ThemePref; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]

export function ThemeToggle() {
  const [pref, setPref] = useState<ThemePref>(readThemePref)
  const choose = (p: ThemePref) => {
    setPref(p)
    applyThemePref(p)
  }
  return (
    <div className="segmented" role="group" aria-label="Theme">
      {OPTIONS.map((o) => (
        <button key={o.value} type="button" aria-pressed={pref === o.value} onClick={() => choose(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}
