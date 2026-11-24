import type { Catalog } from '../../catalog'

export const search: Catalog['search'] = {
  pageTitle: 'Búsqueda de prueba',
  heading: 'Búsqueda de prueba',
  intro:
    'Haz una pregunta como la haría un equipo de planta y mira qué chunks recuperaría el copiloto, del más cercano al más lejano.',
  providerDown:
    'El proveedor de embeddings no funciona: cada pregunta se convierte primero en embedding, así que las búsquedas fallarán hasta que vuelva a estar disponible.',
  providerDownWithError:
    'El proveedor de embeddings no funciona: cada pregunta se convierte primero en embedding, así que las búsquedas fallarán hasta que vuelva a estar disponible ({{error}}).',
  form: {
    label: 'Búsqueda',
    question: 'Pregunta',
    hint: 'Enter busca, Mayús+Enter añade una línea. Las preguntas nunca se registran ni se ponen en la URL.',
    topK: 'Top k',
    submit: 'Buscar',
    searching: 'Buscando…',
    loading: 'Buscando',
    results: 'Resultados',
  },
  problem: {
    queryEmpty: 'Escribe una pregunta.',
    queryTooLong: 'Como máximo {{max}} caracteres (ahora {{n}}).',
    topK: 'Un número entero del 1 al 50.',
    minSimilarity: 'Un número del 0 al 1, o vacío para ninguno.',
    providerFailed:
      'El proveedor de embeddings ha fallado: no se ha podido convertir la pregunta en embedding, así que no se ha buscado nada. Inténtalo de nuevo en un momento.',
  },
  empty: {
    introTitle: 'Los resultados aparecen aquí',
    introDescription:
      'Cada resultado es un chunk: lo cerca que está de la pregunta (similitud coseno; 1 es la misma dirección), su documento y en qué parte de él está. Cada búsqueda convierte la pregunta en embedding una vez.',
    minTitle: 'Nada ha alcanzado la similitud mínima',
    minDescription: 'Ninguno de los {{topK}} primeros chunks ha llegado a {{min}}.',
    clearMin: 'Quitar el mínimo y volver a buscar',
    noSearchableTitle: 'No hay documentos en los que buscar',
    noSearchableDescription: 'Todos los documentos que coinciden tienen embeddings de otro modelo.',
    nothingTitle: 'Nada en lo que buscar',
    nothingTenants: 'Estas organizaciones no tienen documentos.',
    nothingEmpty: 'La base de conocimiento está vacía: sube un documento primero.',
  },
  skipped: {
    text_one:
      '{{count}} documento se ha quedado fuera: sus embeddings son de otro modelo (o de antes de que se registraran los modelos), así que sus vectores no se pueden comparar. Reprocésalo para poder buscar en él.',
    text_other:
      '{{count}} documentos se han quedado fuera: sus embeddings son de otro modelo (o de antes de que se registraran los modelos), así que sus vectores no se pueden comparar. Reprocésalos para poder buscar en ellos.',
    include: 'Incluirlos',
    review: 'Revisar documentos desactualizados',
  },
  tenants: {
    label: 'Organizaciones',
    popover: 'Organizaciones en las que buscar',
    all: 'Todas las organizaciones',
    some_one: '{{count}} organización',
    some_other: '{{count}} organizaciones',
    loading: 'Cargando organizaciones…',
    failed: 'No se han podido cargar las organizaciones.',
    none: 'Aún no hay organizaciones.',
    counts: '{{docs}} docs · {{chunks}} ch',
    noDocuments: 'sin documentos',
    note: 'El copiloto buscará en la organización de un cliente más la organización compartida <mono>ayo</mono>, nunca entre clientes. Todas las organizaciones es para administradores.',
  },
  options: {
    button: 'Opciones',
    buttonSet_one: 'Opciones, {{count}} activa',
    buttonSet_other: 'Opciones, {{count}} activas',
    label: 'Opciones de búsqueda',
    min: 'Similitud mínima',
    minHint: 'De 0 a 1. Los chunks por debajo se quitan del top k. Vacío los mantiene todos.',
    minPlaceholder: 'Ninguna',
    outdated: 'Incluir documentos con embeddings de otro modelo',
    outdatedHint:
      'Sus vectores están en otro espacio, así que su similitud significa poco. Se marcan en los resultados.',
  },
  result: {
    label: 'Resultado {{rank}}',
    similarity: 'Similitud',
    otherModel: 'Otro modelo',
    otherModelHint:
      'Embeddings de un modelo distinto de {{config}}: esta similitud no es comparable. Reprocesa el documento.',
    currentConfig: 'el actual',
    chars: '{{n}} caracteres',
    noHeading: 'Antes del primer encabezado',
    chunk: 'chunk {{index}}',
    more: 'Mostrar más',
    less: 'Mostrar menos',
  },
  summary: {
    label: 'Resumen de la búsqueda',
    results_one: '{{count}} resultado',
    results_other: '{{count}} resultados',
    top: 'top {{n}}',
    min: 'mín. {{n}}',
    allTenants: 'todas las organizaciones',
    otherModels: 'otros modelos incluidos',
    timings: 'Embedding {{embed}} · Búsqueda {{search}} · Total {{total}}',
    ms: '{{n}} ms',
    details: 'Detalles',
    embeddedQuery: 'Consulta convertida en embedding (input_type: {{type}})',
    embedderConfig: 'Configuración de embeddings buscada',
    chunkerConfig: 'Configuración de chunks actual',
    skipped: 'Omitidos (embedder_mismatch)',
  },
}
