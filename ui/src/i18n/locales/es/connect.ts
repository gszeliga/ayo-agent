import type { Catalog } from '../../catalog'

export const connect: Catalog['connect'] = {
  pageTitle: 'Conectar',
  title: 'Conéctate a la API de AYO',
  description: 'La API de administración con la que esta interfaz gestiona los documentos.',
  address: 'Dirección de la API',
  key: 'Clave de administración',
  showKey: 'Mostrar clave',
  hideKey: 'Ocultar clave',
  submit: 'Conectar',
  checking: 'Comprobando…',
  note: 'Solo para uso interno: la clave se guarda en esta pestaña hasta que la cierres.',
  fieldError: {
    address: 'Escribe una dirección http(s) sin ruta, como https://host:8000.',
    keyMissing: 'Escribe la clave de administración.',
    keyRejected: 'Clave rechazada.',
  },
  notice: {
    keyRejected: 'Se ha rechazado tu clave. Vuelve a conectarte con una clave válida.',
  },
}
