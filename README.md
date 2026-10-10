# Informe de evaluación de cursos (Streamlit)

App que procesa un `.zip` con cuestionarios de evaluación de la calidad de acciones formativas
(PDF rellenables del modelo SEPE/FUNDAE) y genera el informe **«Informe Curso – [Nombre del curso]»** en PDF.

## Contenido del informe
1. **Ficha del curso**: nombre (denominación AAFF), sociedad bonificada (Nº expediente), Nº AAFF / Nº grupo y nº de cuestionarios.
2. **Análisis cuantitativo**: tabla con la puntuación media y el nivel de satisfacción de los apartados 1 a 10
   (1,00–2,99 «No satisfactorio»; 3,00–4,00 «Satisfactorio»; las cifras no se redondean, se truncan), gráfico
   y un subapartado por cada elemento con el detalle de sus sub-ítems.
3. **Análisis de comentarios** (ítem 11): elemento valorado, valor (positivo/negativo/neutro), frecuencia
   (nº de participantes) y 2 comentarios ilustrativos por elemento.
4. **Conclusiones y recomendaciones**: valoración global (0–10), resumen ejecutivo, nivel de satisfacción general,
   fortalezas y áreas de mejora (con 2 comentarios cada una) y tabla de ajustes (punto de mejora, comentario y acción).

## Criterios de cálculo
- Las respuestas se leen de los **campos del formulario** del PDF (no del texto impreso). «No contesta» se excluye.
- Media de cada apartado = media de las medias de sus sub-ítems.
- **Apartado 4**: incluye las columnas de formadores y de tutores.
- **Apartado 7**: solo se calcula con cuestionarios de modalidad Teleformación o Mixta (si todo es presencial: «No aplica»).
  Se puede forzar desde la barra lateral.
- **Apartado 8** (Sí/No): equivalencia Sí = 4, No = 1 para obtener la media; el detalle muestra el % de «Sí».
- **Apartado 10**: media del grado de satisfacción; el % que recomendaría el curso (10.1) se añade como nota.
- Valoración global (0–10) = (media de los apartados 1-7, 9 y 10 − 1) / 3 × 10.

## Análisis de comentarios
- **Por defecto**: motor de reglas sin conexión (`comentarios.py`), con un diccionario de elementos y un léxico
  de opinión que se pueden ampliar.
- **Opcional, con IA**: activando la opción en la barra lateral y con una clave de la API de Anthropic, Claude
  clasifica los comentarios y redacta resumen, fortalezas, mejoras y recomendaciones. Las cifras siempre se
  calculan en código y las citas que devuelva la IA se comprueban contra los comentarios originales.

## Ejecutar en local
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Desplegar en Streamlit Community Cloud
1. Sube esta carpeta a un repositorio de GitHub.
2. En https://share.streamlit.io → **Create app** → elige el repositorio, la rama y `app.py` como archivo principal.
3. (Opcional, IA) En **Settings → Secrets** pega: `ANTHROPIC_API_KEY = "sk-ant-..."`.

## Probar sin cuestionarios reales
```bash
python herramientas/generar_cuestionarios_prueba.py Cuestionario_ejemplo.pdf prueba.zip 15
```

## Estructura
| Archivo | Función |
|---|---|
| `app.py` | Interfaz Streamlit |
| `extractor.py` | Lectura del .zip y de los campos de cada cuestionario |
| `analisis.py` | Ficha, medias, niveles, conclusiones y recomendaciones |
| `comentarios.py` | Análisis de comentarios por reglas |
| `ia.py` | Análisis opcional con la API de Anthropic |
| `informe_pdf.py` | Maquetación del PDF |
