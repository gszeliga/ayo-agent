# PRO-014 Control de sellado
## 1. Objeto
Este procedimiento define cómo verificar la presión y la temperatura de sellado en la línea de envasado, para evitar fugas en el envase final.

## 2. Alcance
Aplica a todas las selladoras de la planta de Sevilla, en los tres turnos. ¿Y las máquinas en pruebas? También, salvo indicación expresa del responsable de mantenimiento.

## 3. Pasos
### 3.1 Preparación
- Limpiar la mordaza con un paño sin pelusa.
- Comprobar que el termopar marca entre 180 °C y 190 °C.
- Registrar la lectura en la hoja de turno.

### 3.2 Medición
| Parámetro | Mínimo | Máximo | Unidad |
|-----------|--------|--------|--------|
| Presión   | 2,5    | 3,0    | bar    |
| Tiempo    | 0,8    | 1,2    | s      |

Si la presión sale del rango, ¡detener la línea! y avisar al jefe de turno.

```bash
# Exportar las lecturas del PLC
plc-export --linea 3 --desde "06:00"
```

## 4. Registros
Las lecturas se guardan durante dos años en el archivo de calidad. Señalización: etiqueta roja en la selladora afectada hasta su revisión.
