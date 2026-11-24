import type { Catalog } from '../../catalog'

export const upload: Catalog['upload'] = {
  uploadTitle: 'Subir un documento',
  replaceTitle: 'Sustituir documento',
  uploadDescription:
    'Un archivo Markdown se divide en chunks según sus encabezados y se generan sus embeddings.',
  replaceDescription: 'Sustituye el contenido de {{name}}. Los chunks se vuelven a generar.',
  providerDown:
    'El proveedor de embeddings no funciona: las subidas fallarán hasta que vuelva a estar disponible.',
  providerDownWithError:
    'El proveedor de embeddings no funciona: las subidas fallarán hasta que vuelva a estar disponible ({{error}}).',
  file: {
    label: 'Archivo Markdown',
    prompt: '<choose>Elige un archivo</choose> o suéltalo aquí',
    format: 'Markdown (.md), UTF-8',
    remove: 'Quitar archivo',
  },
  tenant: {
    label: 'Organización',
    hint: 'Minúsculas, dígitos y guiones, de 2 a 63 caracteres.',
  },
  title: {
    label: 'Título (opcional)',
    placeholder: 'Del primer encabezado #; si no hay, el nombre del archivo',
  },
  advanced: 'Avanzado',
  sourceKey: {
    label: 'Clave de origen',
    hint: 'Identifica el documento dentro de la organización; volver a subir la misma lo sustituye.',
    placeholder: 'El nombre del archivo',
  },
  force: { label: 'Forzar reindexado', hint: 'Aunque no haya cambiado nada.' },
  existing:
    'Ya existe un documento con este nombre en {{tenant}}: subirlo lo sustituye ({{name}}, actualizado {{when}}).',
  problem: {
    fileMissing: 'Elige un archivo Markdown.',
    notMarkdown: 'Elige un archivo Markdown (.md).',
    empty: 'El archivo está vacío.',
    tooLarge: 'Supera el límite de {{limit}}.',
    tooLargeUnknown: 'El archivo supera el límite de subida.',
    tenantMissing: 'Escribe una organización.',
    tenantInvalid: 'Minúsculas, dígitos y guiones, de 2 a 63 caracteres.',
    providerFailed:
      'El proveedor de embeddings ha fallado tras varios intentos. No se ha guardado nada; inténtalo más tarde.',
    cancelled:
      'Subida cancelada. Si la API ya había recibido el archivo, puede que aún lo indexe: revisa la lista en un momento.',
  },
  cancel: 'Cancelar',
  upload: 'Subir',
  replace: 'Sustituir',
  busy: 'Subiendo e indexando…',
  toast: {
    upToDate: 'Ya estaba al día: no ha cambiado nada.',
    upToDateHint: 'Usa Forzar reindexado para reconstruirlo de todos modos.',
    indexed: 'Indexado {{name}}: {{chunks}}',
    replaced: 'Sustituido {{name}}: {{chunks}}',
    chunks_one: '{{count}} chunk',
    chunks_other: '{{count}} chunks',
  },
}
