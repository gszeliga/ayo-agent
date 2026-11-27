/** The shell (header, nav, menus, crash and 404 pages) and the shared formatters' words. */
export const common = {
  shell: {
    banner: 'Internal use only: this UI sends the shared admin key from your browser.',
    dismiss: 'Dismiss',
    mainNav: 'Main',
    testChat: 'Test chat',
    knowledgeBase: 'Knowledge base',
    documents: 'Documents',
    search: 'Search',
    indexingSettings: 'Indexing settings',
    disconnect: 'Disconnect',
    // The header's last button; its visible text is the host.
    connectionMenu: 'Connection and preferences: {{host}}',
    // <host/> is the API's host, in monospace (a component, so it is never parsed).
    connectedTo: 'Connected to <host/>',
  },
  status: {
    trigger: 'Service status: database {{database}}, embeddings {{embeddings}}',
    state: { up: 'up', down: 'down', unknown: 'status unknown' },
    // The header's pill (its name is `trigger`, so a screen reader hears each service).
    summary: {
      ok: 'All systems ok',
      databaseDown: 'Database down',
      embeddingsDown: 'Embeddings down',
      bothDown: 'Database and embeddings down',
      checking: 'Checking…',
      unknown: 'Status unknown',
    },
  },
  theme: {
    label: 'Theme',
    choice: { light: 'Light', dark: 'Dark', system: 'System' },
  },
  language: {
    label: 'Language',
    trigger: 'Language: {{choice}}',
    system: 'System',
    systemCurrent: 'system',
  },
  crash: {
    newVersionTitle: 'A new version of this page is available',
    newVersionDescription: 'Reload to get it.',
    title: 'Something went wrong',
    description:
      'This page failed to show. Reloading usually helps; if not, the details are in the browser console.',
    reload: 'Reload',
    backToDocuments: 'Back to documents',
  },
  notFound: {
    title: 'Page not found',
    description: 'There is nothing at this address.',
    goToDocuments: 'Go to documents',
  },
  retry: 'Retry',
  // Skeletons while a lazy page or the Markdown renderer loads.
  loading: {
    document: 'Loading document',
    settings: 'Loading settings',
    search: 'Loading search',
    chat: 'Loading chat',
    content: 'Loading content',
  },
  // <phrase/> is the text to type, shown in bold (a component, so it is never parsed).
  confirmByTyping: 'Type <phrase/> to confirm',
  copy: { copied: 'Copied', unavailable: 'Copy unavailable' },
  // The UI's own wording of a failed call; the API's own `msg` is shown as received.
  errors: {
    unreachable: "Can't reach the API at {{baseUrl}}. Check the URL and that the API is running.",
    corsRefused:
      'The API at {{baseUrl}} answers, but refuses requests from this page. Add {{origin}} to CORS_ALLOWED_ORIGINS and restart the API.',
    unexpectedStatus: 'The API answered HTTP {{status}}',
  },
  time: {
    justNow: 'just now',
    minutesAgo: '{{n}} min ago',
    hoursAgo: '{{n}} h ago',
    daysAgo: '{{n}} d ago',
  },
  size: { bytes: '{{n}} B', kilobytes: '{{n}} KB', megabytes: '{{n}} MB' },
}
