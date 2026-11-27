import type { Catalog } from '../../catalog'

export const common: Catalog['common'] = {
  shell: {
    banner:
      'Solo para uso interno: esta interfaz envía la clave de administración compartida desde tu navegador.',
    dismiss: 'Cerrar',
    mainNav: 'Principal',
    testChat: 'Chat de prueba',
    knowledgeBase: 'Base de conocimiento',
    documents: 'Documentos',
    search: 'Búsqueda',
    indexingSettings: 'Ajustes de indexación',
    disconnect: 'Desconectar',
  },
  status: {
    trigger: 'Estado del servicio: base de datos {{database}}, embeddings {{embeddings}}',
    database: 'Base de datos',
    embeddings: 'Embeddings',
    state: { up: 'OK', down: 'sin servicio', unknown: 'estado desconocido' },
  },
  theme: {
    label: 'Tema',
    trigger: 'Tema: {{choice}}',
    current: { light: 'claro', dark: 'oscuro', system: 'sistema' },
    choice: { light: 'Claro', dark: 'Oscuro', system: 'Sistema' },
  },
  language: {
    label: 'Idioma',
    trigger: 'Idioma: {{choice}}',
    system: 'Sistema',
    systemCurrent: 'sistema',
  },
  crash: {
    newVersionTitle: 'Hay una versión nueva de esta página',
    newVersionDescription: 'Recarga para obtenerla.',
    title: 'Algo ha fallado',
    description:
      'No se ha podido mostrar esta página. Recargar suele ayudar; si no, los detalles están en la consola del navegador.',
    reload: 'Recargar',
    backToDocuments: 'Volver a documentos',
  },
  notFound: {
    title: 'Página no encontrada',
    description: 'No hay nada en esta dirección.',
    goToDocuments: 'Ir a documentos',
  },
  retry: 'Reintentar',
  loading: {
    document: 'Cargando documento',
    settings: 'Cargando ajustes',
    search: 'Cargando búsqueda',
    chat: 'Cargando chat',
    content: 'Cargando contenido',
  },
  confirmByTyping: 'Escribe <phrase/> para confirmar',
  copy: { copied: 'Copiado', unavailable: 'No se puede copiar' },
  errors: {
    unreachable:
      'No se puede conectar con la API en {{baseUrl}}. Comprueba la URL y que la API esté en marcha.',
    corsRefused:
      'La API en {{baseUrl}} responde, pero rechaza las peticiones de esta página. Añade {{origin}} a CORS_ALLOWED_ORIGINS y reinicia la API.',
    unexpectedStatus: 'La API ha respondido HTTP {{status}}',
  },
  time: {
    justNow: 'ahora mismo',
    minutesAgo: 'hace {{n}} min',
    hoursAgo: 'hace {{n}} h',
    daysAgo: 'hace {{n}} d',
  },
  size: { bytes: '{{n}} B', kilobytes: '{{n}} KB', megabytes: '{{n}} MB' },
}
