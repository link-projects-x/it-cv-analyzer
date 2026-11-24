/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend base URL. Unset: the app uses the mock API. */
  readonly VITE_API_URL?: string
  /** "local": read and match the CV in the browser against public/data (static site, no backend). */
  readonly VITE_API_MODE?: string
}
