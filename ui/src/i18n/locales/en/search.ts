/** The test search: form, options, organization picker, results, summary, empty states. */
export const search = {
  pageTitle: 'Test search',
  heading: 'Test search',
  intro:
    'Ask a question the way a plant team would and see which chunks the copilot would retrieve, nearest first.',
  providerDown:
    'The embedding provider is down: every question is embedded first, so searches fail until it is back.',
  // The API's own error text, as received, in the parentheses.
  providerDownWithError:
    'The embedding provider is down: every question is embedded first, so searches fail until it is back ({{error}}).',
  form: {
    label: 'Search',
    question: 'Question',
    hint: 'Enter searches, Shift+Enter adds a line. Questions are never logged or put in the URL.',
    topK: 'Top k',
    submit: 'Search',
    searching: 'Searching…',
    loading: 'Searching',
    results: 'Results',
  },
  problem: {
    queryEmpty: 'Type a question.',
    queryTooLong: 'At most {{max}} characters (now {{n}}).',
    topK: 'A whole number from 1 to 50.',
    minSimilarity: 'A number from 0 to 1, or empty for none.',
    providerFailed:
      'The embedding provider failed: the question could not be embedded, so nothing was searched. Try again in a moment.',
  },
  empty: {
    introTitle: 'Results appear here',
    introDescription:
      'Each result is a chunk: how close it is to the question (cosine similarity, 1 is the same direction), its document, and where in it the chunk sits. Each search embeds the question once.',
    minTitle: 'Nothing reached the minimum similarity',
    minDescription: 'None of the top {{topK}} chunks scored {{min}} or more.',
    clearMin: 'Clear the minimum and search again',
    noSearchableTitle: 'No searchable documents',
    noSearchableDescription: 'Every matching document was embedded with another model.',
    nothingTitle: 'Nothing to search',
    nothingTenants: 'These tenants have no documents.',
    nothingEmpty: 'The knowledge base is empty: upload a document first.',
  },
  skipped: {
    text_one:
      '{{count}} document was left out: it was embedded with a different model (or before models were recorded), so its vectors can’t be compared. Reprocess it to make it searchable.',
    text_other:
      '{{count}} documents were left out: they were embedded with a different model (or before models were recorded), so their vectors can’t be compared. Reprocess them to make them searchable.',
    include: 'Include them',
    review: 'Review outdated documents',
  },
  tenants: {
    label: 'Tenants',
    popover: 'Tenants to search',
    all: 'All tenants',
    // Three or more (one or two are named).
    some_one: '{{count}} tenants',
    some_other: '{{count}} tenants',
    loading: 'Loading tenants…',
    failed: 'Couldn’t load the tenants.',
    none: 'No tenants yet.',
    counts: '{{docs}} docs · {{chunks}} ch',
    noDocuments: 'no documents',
    // <mono> is the shared tenant's id.
    note: 'The copilot will search one customer’s tenant plus the shared <mono>ayo</mono> tenant, never across customers. All tenants is for administrators.',
  },
  options: {
    button: 'Options',
    // The button's name when options are set (the badge shows only the number).
    buttonSet_one: 'Options, {{count}} set',
    buttonSet_other: 'Options, {{count}} set',
    label: 'Search options',
    min: 'Minimum similarity',
    minHint: '0 to 1. Chunks below it are dropped from the top k. Empty keeps them all.',
    minPlaceholder: 'None',
    outdated: 'Include documents embedded with another model',
    outdatedHint:
      'Their vectors live in another space, so their similarity means little. They are flagged in the results.',
  },
  result: {
    label: 'Result {{rank}}',
    similarity: 'Similarity',
    otherModel: 'Other model',
    otherModelHint:
      'Embedded with another model than {{config}}: this similarity is not comparable. Reprocess the document.',
    currentConfig: 'the current one',
    chars: '{{n}} chars',
    noHeading: 'Before the first heading',
    chunk: 'chunk {{index}}',
    more: 'Show more',
    less: 'Show less',
  },
  summary: {
    label: 'Search summary',
    results_one: '{{count}} result',
    results_other: '{{count}} results',
    top: 'top {{n}}',
    min: 'min {{n}}',
    allTenants: 'all tenants',
    otherModels: 'other models included',
    timings: 'Embedding {{embed}} · Search {{search}} · Total {{total}}',
    ms: '{{n}} ms',
    details: 'Details',
    embeddedQuery: 'Embedded query (input_type: {{type}})',
    embedderConfig: 'Embedder config searched',
    chunkerConfig: 'Current chunker config',
    skipped: 'Skipped (embedder_mismatch)',
  },
}
