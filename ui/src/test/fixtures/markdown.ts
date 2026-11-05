/** A procedure with what the renderer must handle: a table, links, an image, raw HTML. */
export const PROCEDURE_MD = `# PRO-014 Control de sellado

## 1. Objeto

Verificar la presión de la junta antes de cada turno. Ver la [norma interna](https://intranet.example/normas/14).

## 2. Valores

| Equipo | Presión mínima | Presión máxima |
|---|---|---|
| Selladora A | 3,8 bar | 4,4 bar |
| Selladora B | 4,0 bar | 4,6 bar |

![Esquema de la junta](https://tracker.example/junta.png)

<script>window.__pwned = true</script>
<b onclick="alert(1)">texto en HTML</b>

[enlace peligroso](javascript:alert(1))
`
