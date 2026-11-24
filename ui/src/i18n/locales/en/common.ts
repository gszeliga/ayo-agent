/** The shell (header, nav, menus, crash and 404 pages) and the shared formatters' words. */
export const common = {
  shell: {
    banner: 'Internal use only: this UI sends the shared admin key from your browser.',
    dismiss: 'Dismiss',
    mainNav: 'Main',
    testChat: 'Test chat',
    knowledge: 'Knowledge',
    documents: 'Documents',
    search: 'Search',
    indexingSettings: 'Indexing settings',
    disconnect: 'Disconnect',
  },
  status: {
    trigger: 'Service status: database {{database}}, embeddings {{embeddings}}',
    database: 'Database',
    embeddings: 'Embeddings',
    state: { up: 'up', down: 'down', unknown: 'status unknown' },
  },
  theme: {
    label: 'Theme',
    trigger: 'Theme: {{choice}}',
    // In the trigger's name: "Theme: dark".
    current: { light: 'light', dark: 'dark', system: 'system' },
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
  time: {
    justNow: 'just now',
    minutesAgo: '{{n}} min ago',
    hoursAgo: '{{n}} h ago',
    daysAgo: '{{n}} d ago',
  },
  size: { bytes: '{{n}} B', kilobytes: '{{n}} KB', megabytes: '{{n}} MB' },
}
