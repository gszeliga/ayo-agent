/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API base URL default for the connect screen (build time); else the page's origin. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
