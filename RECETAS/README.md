# Repositorio de Recetas Médicas (`RECETAS/`)

Este directorio almacena las recetas médicas familiares vigentes (junto con su archivo `.txt` obligatorio) y el archivo histórico de recetas sustituidas o vencidas.

## Criterio Obligatorio de Nombres de Archivo
**Toda receta médica almacenada en este directorio DEBE incluir en su nombre de archivo los nombres abreviados de los medicamentos principales prescritos y contar con su archivo `.txt` homónimo.**

### Formato:
`YYYYMMDD_Receta_[Medicamento1]_[Medicamento2]..._[Profesional/Institución].[ext]`

### Ejemplos:
* `20261019_Receta_MedicamentoA_MedicamentoB_Dr_Nombre_Apellido.jpeg` (y su `.txt` homónimo)
* `20260715_Receta_MedicamentoC_Clinica_GES.jpeg` (y su `.txt` homónimo)

## Reglas de Organización y Archivo:
1. **Raíz (`RECETAS/`):** Contiene **únicamente recetas médicas vigentes y activas** junto con su resumen `.txt`.
2. **Histórico (`RECETAS/archivadas/`):** Cuando el médico emita una nueva receta que reemplace o renueve tratamientos previos para dichos medicamentos, la receta anterior (y su `.txt`) debe trasladarse de inmediato a esta subcarpeta de archivo.
