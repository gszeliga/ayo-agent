/** The test chat: the cases column, the case view, new conversations, phases, formatters. */
export const chat = {
  pageTitle: 'Test chat',
  // Shared by the rows, the case header and the delete dialog.
  untitled: 'Untitled case',
  turns_one: '{{count}} turn',
  turns_other: '{{count}} turns',
  conversation: 'Conversation',
  // By the API's value; the URL and the API keep the value.
  phase: {
    understand: 'Understand',
    challenge: 'Challenge',
    analyse: 'Analyse',
    action: 'Action',
    followup: 'Follow-up',
    closed: 'Closed',
  },
  // `chat/format.ts`: {{n}} is a number already formatted for the language.
  format: {
    cost: '${{n}}',
    costBelow: '<${{n}}',
    tokens_one: '{{count}} token',
    tokens_other: '{{count}} tokens',
    tokensThousands: '{{n}}k tokens',
    tokensMillions: '{{n}}M tokens',
    milliseconds: '{{n}} ms',
    seconds: '{{n}} s',
  },
  page: {
    casesList: 'Cases list',
    resizeCasesList: 'Resize cases list',
    loadingCase: 'Loading case',
    pickTitle: 'Pick a case',
    pickDescription: 'Choose a case from the list, or start a new conversation.',
  },
  cases: {
    heading: 'Cases',
    list: 'Cases',
    newConversation: 'New conversation',
    loading: 'Loading cases',
    noMatchTitle: 'No cases match',
    noMatchDescription: 'Try another search or filter.',
    clearFilters: 'Clear filters',
    emptyTitle: 'No conversations yet',
    emptyDescription: 'Cases appear here once someone talks to the copilot.',
    moreFailed: 'More cases could not be loaded.',
    loadingMore: 'Loading…',
    loadMore: 'Load more',
    rail: 'Cases list (collapsed)',
    // After the count, for screen readers: "12 cases".
    railSuffix_one: ' cases',
    railSuffix_other: ' cases',
  },
  filters: {
    search: 'Search cases',
    searchPlaceholder: 'Search what happens',
    tenant: 'Tenant',
    allTenants: 'All tenants',
    phase: 'Phase',
    allPhases: 'All phases',
    state: 'State',
    // By value (`CaseState`).
    states: { all: 'All', open: 'Open', closed: 'Closed' },
  },
  row: {
    pending_one: '{{count}} pending',
    pending_other: '{{count}} pending',
    overdue_one: '{{count}} overdue',
    overdue_other: '{{count}} overdue',
    otherChannel: 'Other channel',
    // Before the relative time, for screen readers.
    updated: 'Updated ',
  },
  // `PanelToggle`, by panel; `PanelResizer`.
  panel: {
    hide: { cases: 'Hide cases', inspector: 'Hide inspector' },
    show: { cases: 'Show cases', inspector: 'Show inspector' },
    width: '{{n}} pixels wide',
  },
  header: { refresh: 'Refresh', export: 'Export', delete: 'Delete' },
  stepper: {
    label: 'Phases',
    // For screen readers, after the phase's name.
    state: { completed: 'completed', current: 'current', notStarted: 'not started' },
  },
  // <to/> is the new phase's name, in bold.
  phaseMarker: 'Moved to <to/> (from {{from}})',
  turn: {
    label: 'Turn {{n}}',
    trace: 'Turn {{n}} · trace',
    // Before each message, for screen readers.
    user: 'User: ',
    copilot: 'Copilot: ',
    copyReply: 'Copy reply',
  },
  turnList: { loading: 'Loading conversation', empty: 'No messages yet.' },
  earlier: {
    failed: 'Earlier turns could not be loaded.',
    loading: 'Loading…',
    load: 'Load earlier turns',
    start: 'Start of the conversation',
  },
  pending: { sending: 'Sending…', answering: 'The copilot is answering' },
  composer: {
    label: 'Message',
    send: 'Send',
    hint: 'Enter sends, Shift+Enter adds a line. Each message calls the language model (billed).',
  },
  // `sendErrors.ts`, by problem; the API's own `msg` goes in {{message}} as received.
  sendError: {
    unreachable:
      "Can't reach the API, so the message may not have arrived. Send it again, or reload the case to see whether it did.",
    caseClosed: 'This case is closed: it takes no more messages.',
    conflict:
      'Another message in this conversation was saved while yours was being answered. Nothing of yours was stored: reload the case, then send it again.',
    refused: 'The API refused the message: {{message}}',
    modelFailed: 'The language model failed, so nothing was stored. You can send it again.',
    noModel:
      'The API has no language model configured (OPENROUTER_API_KEY), so nothing was stored.',
    sendAgain: 'Send again',
    reload: 'Reload case',
  },
  // `readOnly.ts`, by reason.
  readOnly: {
    closed: 'This case is closed: it can be read here but not continued.',
    otherChannel: 'This case came from another channel: it can be read here but not continued.',
  },
  notFound: {
    title: 'This case no longer exists',
    description: 'It may have been deleted, or the link is wrong.',
    back: 'Back to the cases',
  },
  deleteCase: {
    title: 'Delete this case?',
    // {{turns}}, {{annotations}}, {{actions}}: the counts below, already worded.
    what: 'It is removed for good, with everything it holds: {{turns}} (messages, replies and traces), {{annotations}}, {{actions}}. There is no undo.',
    whatWithSummary:
      'It is removed for good, with everything it holds: {{turns}} (messages, replies and traces), {{annotations}}, {{actions}} and its AI summary. There is no undo.',
    annotations_one: '{{count}} annotation',
    annotations_other: '{{count}} annotations',
    actions_one: '{{count}} action',
    actions_other: '{{count}} actions',
    newCase: "A later message on this conversation's session starts a new case.",
    cancel: 'Cancel',
    deleting: 'Deleting…',
    confirm: 'Delete case',
    done: 'Case deleted',
    alreadyGone: 'The case was already deleted',
  },
  // A turn that changed phase, in the Trace tab and the export.
  phaseChange: '{{from}} → {{to}}',
  usage: { calls_one: '{{count}} call', calls_other: '{{count}} calls' },
  inspector: {
    title: 'Inspector',
    tabs: { state: 'State', actions: 'Actions', trace: 'Trace', summary: 'Summary' },
    resize: 'Resize inspector',
    drawerDescription:
      'What the case holds: its facts, annotations, actions, turn traces and summaries.',
  },
  rail: {
    label: 'Inspector (collapsed)',
    tabs: 'Inspector tabs',
    // By tab (`InspectorTab`).
    show: {
      state: 'Show state',
      actions: 'Show actions',
      trace: 'Show trace',
      summary: 'Show summary',
    },
    showActionsOverdue_one: 'Show actions ({{count}} overdue)',
    showActionsOverdue_other: 'Show actions ({{count}} overdue)',
  },
  state: {
    facts: 'Facts',
    fact: { what: 'What', where: 'Where', since: 'Since', standard: 'Standard' },
    notRecorded: 'Not recorded yet',
    // By the API's event type.
    groups: {
      hypothesis: 'Hypotheses',
      hypothesis_discarded: 'Discarded hypotheses',
      validated_cause: 'Validated cause',
      evidence: 'Evidence',
    },
    discardNote:
      'A discard is recorded on its own: it is not linked to the hypothesis it rules out.',
    none: 'None yet',
    inPhase: 'In {{phase}}',
  },
  actions: {
    list: 'Actions',
    none: 'No actions yet',
    owner: 'Owner',
    due: 'Due',
    done: 'Done',
    pending: 'Pending',
    overdue: 'Overdue',
  },
  totals: { title: 'Case totals', turns: 'Turns', summary: 'AI summary' },
  trace: {
    neverShown:
      "Never shown: chunk text, tool arguments and the model's reasoning. The API does not return them.",
    loading: 'Loading traces',
    none: 'No turns yet',
    list: 'Traces',
    entry: 'Trace of turn {{n}}',
    capped: 'Capped',
    retrievalFailed: 'Retrieval failed',
    refused_one: '{{count}} refused',
    refused_other: '{{count}} refused',
    toolCalls: 'Tool calls',
    noCalls: 'None',
    accepted: 'accepted',
    refusedCall: 'refused',
    missing: 'missing:',
    retrieved: 'Retrieved',
    // <error/> is the API's error code, in monospace.
    searchFailed: 'The knowledge search failed: <error/>',
    nothing: 'Nothing',
    // Before the similarity, for screen readers.
    similarity: 'Similarity ',
    deletedDocument: 'Deleted document',
    untitledDocument: 'Untitled document',
    changedSince: 'Changed since',
    changedSinceTitle: 'The document was reprocessed or replaced since this turn',
    chunk: '· chunk #{{n}}',
    detail: {
      model: 'Model',
      prompts: 'Prompts',
      calls: 'Calls',
      tokens: 'Tokens',
      cost: 'Cost',
      duration: 'Duration',
      time: 'Time',
    },
    notReported: 'Not reported',
    tokensInOut: '{{total}} ({{in}} in, {{out}} out)',
  },
  newConversation: {
    title: 'New conversation',
    description: 'The case is created by the first message, for this tenant.',
    loadingTenants: 'Loading tenants…',
    tenantsFailed: 'The tenants could not be loaded.',
    noTenants: 'No tenants yet: a tenant appears once it has a document.',
    tenant: 'Tenant',
    cancel: 'Cancel',
    start: 'Start',
    noDraftTitle: 'Start a new conversation',
    noDraftDescription: 'Pick the tenant; the first message opens the case.',
    firstMessage: 'Send the first message to open a case.',
  },
}
