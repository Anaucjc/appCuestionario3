"""
App Streamlit: informe de evaluación de acciones formativas.

Carga un .zip con cuestionarios SEPE/FUNDAE en PDF y genera el informe
«Informe Curso – [Nombre del curso]» en PDF.

Ejecutar en local:   streamlit run app.py
"""
from __future__ import annotations

import os
from collections import Counter

import pandas as pd
import streamlit as st

from analisis import fmt, fmt_pct, generar_informe
from extractor import cargar_zip
from informe_pdf import generar_pdf, nombre_archivo

st.set_page_config(page_title="Informe de cursos", page_icon="📊", layout="centered")


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False, max_entries=10)
def procesar_zip(datos: bytes):
    return cargar_zip(datos)


def filtrar(carga, curso: str):
    return [c for c in carga.cuestionarios if (c.curso or "(sin nombre)") == curso]


@st.cache_data(show_spinner=False, max_entries=10)
def informe_con_ia(datos: bytes, curso: str, incluir_tele: bool, clave: str, modelo: str):
    """Se cachea para no repetir la llamada a la API en cada interacción con la página."""
    from ia import mejorar_con_ia
    cuestionarios = filtrar(procesar_zip(datos), curso)
    informe = generar_informe(cuestionarios, incluir_tele_siempre=incluir_tele)
    return mejorar_con_ia(informe, [c.observaciones for c in cuestionarios], clave, modelo)


def clave_api() -> str:
    try:
        return st.secrets.get("ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    except Exception:  # no hay secrets.toml
        return os.environ.get("ANTHROPIC_API_KEY", "")


# --------------------------------------------------------------------------
# Barra lateral: opciones
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Opciones")
    incluir_tele = st.toggle(
        "Valorar el apartado 7 aunque el curso sea presencial",
        value=False,
        help="Por defecto el apartado 7 (teleformación o mixta) solo se calcula con los cuestionarios "
             "cuya modalidad es Teleformación o Mixta, como indica el propio cuestionario.",
    )
    st.divider()
    st.subheader("Análisis con IA (opcional)")
    clave_config = clave_api()
    usar_ia = st.toggle(
        "Mejorar el análisis de comentarios con IA",
        value=False,
        help="Usa la API de Anthropic (Claude) para clasificar los comentarios y redactar el resumen, "
             "fortalezas, áreas de mejora y recomendaciones. Las puntuaciones siempre se calculan en código. "
             "Sin IA se usa un motor de reglas que funciona sin conexión.",
    )
    clave_manual, modelo = "", ""
    if usar_ia:
        if clave_config:
            st.caption("Clave de API configurada en los *secrets* de la app.")
        else:
            clave_manual = st.text_input("Clave de API de Anthropic", type="password")
        from ia import MODELO_POR_DEFECTO
        modelo = st.text_input("Modelo", value=MODELO_POR_DEFECTO)
        st.caption("Los comentarios de los alumnos se enviarán a la API de Anthropic.")

# --------------------------------------------------------------------------
# Cuerpo principal
# --------------------------------------------------------------------------
st.title("📊 Informe de evaluación de cursos")
st.write(
    "Sube un archivo **.zip** con los cuestionarios de evaluación (PDF rellenables del modelo SEPE/FUNDAE) "
    "de una acción formativa. La app extrae las respuestas, calcula las puntuaciones, analiza los "
    "comentarios y genera el informe en PDF."
)

archivo = st.file_uploader("Cuestionarios (.zip)", type=["zip"])

if archivo is None:
    with st.expander("¿Qué contiene el informe?"):
        st.markdown(
            "1. **Ficha del curso**: nombre, sociedad bonificada (Nº expediente), Nº acción formativa / grupo "
            "y número de cuestionarios.\n"
            "2. **Análisis cuantitativo**: puntuación media y nivel de satisfacción de los apartados 1 a 10, "
            "con el detalle de cada sub-ítem.\n"
            "3. **Análisis de comentarios**: elemento valorado, valor (positivo, negativo o neutro), "
            "frecuencia y dos comentarios ilustrativos.\n"
            "4. **Conclusiones y recomendaciones**: valoración global (0-10), resumen ejecutivo, nivel de "
            "satisfacción, fortalezas, áreas de mejora y ajustes recomendados."
        )
    st.stop()

with st.spinner("Leyendo cuestionarios…"):
    carga = procesar_zip(archivo.getvalue())

if carga.errores:
    with st.expander(f"⚠️ {len(carga.errores)} archivo(s) no se han podido procesar", expanded=not carga.cuestionarios):
        for nombre, motivo in carga.errores:
            st.write(f"- `{os.path.basename(nombre)}`: {motivo}")

if not carga.cuestionarios:
    st.error("No se ha encontrado ningún cuestionario válido en el .zip.")
    st.stop()

# Si el zip mezcla varios cursos, se elige cuál informar
cursos = Counter(c.curso or "(sin nombre)" for c in carga.cuestionarios)
if len(cursos) > 1:
    st.warning("El .zip contiene cuestionarios de varios cursos. Elige el curso del que quieres el informe.")
    curso_sel = st.selectbox("Curso", [f"{c}" for c, _ in cursos.most_common()],
                             format_func=lambda c: f"{c} ({cursos[c]} cuestionarios)")
else:
    curso_sel = next(iter(cursos))
cuestionarios = filtrar(carga, curso_sel)

informe, aviso_ia = None, ""
if usar_ia and not (clave_config or clave_manual):
    st.info("Introduce la clave de API en la barra lateral para usar la IA. Mientras tanto se usa el motor de reglas.")
elif usar_ia:
    try:
        with st.spinner("Analizando comentarios con IA…"):
            informe = informe_con_ia(archivo.getvalue(), curso_sel, incluir_tele, clave_config or clave_manual, modelo)
    except Exception as exc:
        aviso_ia = f"No se ha podido usar la IA ({exc}). El informe se ha generado con el motor de reglas."
if informe is None:
    informe = generar_informe(cuestionarios, incluir_tele_siempre=incluir_tele)
if aviso_ia:
    st.warning(aviso_ia)

# --------------------------------------------------------------------------
# Vista previa
# --------------------------------------------------------------------------
f, conc = informe.ficha, informe.conclusiones
st.success(f"{len(cuestionarios)} cuestionarios procesados · **{f.curso}**")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Valoración global", f"{fmt(conc.valoracion_global, 1)} / 10")
c2.metric("Satisfacción", conc.nivel_general)
c3.metric("Satisfechos", fmt_pct(conc.pct_satisfechos))
c4.metric("Recomendaría", fmt_pct(conc.pct_recomienda))

pestanas = st.tabs(["Ficha", "Cuantitativo", "Comentarios", "Conclusiones"])
with pestanas[0]:
    st.table(pd.DataFrame({
        "Campo": ["Nombre del curso", "Sociedad bonificada (Nº expediente)", "Nº acción formativa / Grupo",
                  "Modalidad", "Nº cuestionarios"],
        "Valor": [f.curso, f.expediente, f"{f.num_aaff} / {f.num_grupo}", f.modalidad, str(f.num_cuestionarios)],
    }).set_index("Campo"))
    for aviso in f.avisos:
        st.caption("⚠️ " + aviso)
with pestanas[1]:
    st.dataframe(pd.DataFrame([
        {"Apartado": f"{a.clave}. {a.titulo}", "Puntuación media": fmt(a.media), "Nivel": a.nivel}
        for a in informe.apartados
    ]), hide_index=True)
with pestanas[2]:
    if informe.comentarios.elementos:
        st.dataframe(pd.DataFrame([
            {"Elemento": e.elemento, "Valor": e.valor, "Frecuencia": e.frecuencia,
             "Comentarios": " | ".join(e.ejemplos)}
            for e in informe.comentarios.elementos
        ]), hide_index=True)
    else:
        st.write("No hay comentarios.")
with pestanas[3]:
    st.markdown(f"**Resumen ejecutivo.** {conc.resumen}")
    st.markdown("**Fortalezas**\n" + "\n".join(f"- {x}" for x in conc.fortalezas))
    st.markdown("**Áreas de mejora**\n" + "\n".join(f"- {x}" for x in conc.areas_mejora))
    st.markdown("**Recomendaciones**\n" + "\n".join(f"- **{r.titulo}**: {r.accion}" for r in conc.recomendaciones))

# --------------------------------------------------------------------------
# Descarga
# --------------------------------------------------------------------------
with st.spinner("Generando PDF…"):
    pdf = generar_pdf(informe, [c.archivo for c in cuestionarios], carga.errores)

st.download_button(
    "⬇️ Descargar informe en PDF",
    data=pdf,
    file_name=nombre_archivo(informe),
    mime="application/pdf",
    type="primary",
)
st.caption(f"Análisis de comentarios: {'motor de reglas' if informe.motor == 'reglas' else informe.motor}.")
