// The person's API access code, kept in this browser so it is typed once. Storage can be unavailable (private
// windows, blocked site data), so every access is guarded and the app works without it.
const KEY = 'dou-cv-analyzer.accessCode'

export function readAccessCode(): string {
  try {
    return window.localStorage.getItem(KEY) ?? ''
  } catch {
    return ''
  }
}

export function saveAccessCode(code: string): void {
  try {
    if (code) window.localStorage.setItem(KEY, code)
    else window.localStorage.removeItem(KEY)
  } catch {
    // Not persisted; the code still works for this page load through the in-memory value.
  }
}
