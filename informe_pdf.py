"""
Generación del informe en PDF (reportlab + matplotlib).
"""
from __future__ import annotations

import io
import os
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    CondPageBreak, Image, KeepTogether, ListFlowable, ListItem,
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from xml.sax.saxutils import escape  # noqa: E402

from analisis import Informe, fmt, fmt_pct  # noqa: E402

# --------------------------------------------------------------------------
# Tipografía: DejaVu Sans viene incluida con matplotlib (cubre tildes, ñ, «», –)
# --------------------------------------------------------------------------
_FUENTES = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
try:
    pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(_FUENTES, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", os.path.join(_FUENTES, "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Oblique", os.path.join(_FUENTES, "DejaVuSans-Oblique.ttf")))
    pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold",
                                  italic="DejaVu-Oblique", boldItalic="DejaVu-Bold")
    F, FB, FI = "DejaVu", "DejaVu-Bold", "DejaVu-Oblique"
except Exception:  # pragma: no cover
    F, FB, FI = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"

# Colores
TINTA = colors.HexColor("#1f2933")
TINTA_2 = colors.HexColor("#52514e")
PRIMARIO = colors.HexColor("#1c5cab")
PRIMARIO_CLARO = colors.HexColor("#e8f0fb")
BORDE = colors.HexColor("#d5d9de")
FONDO_ALT = colors.HexColor("#f6f7f8")
OK = colors.HexColor("#0b7a0b")
OK_FONDO = colors.HexColor("#e6f4e6")
KO = colors.HexColor("#b42f2f")
KO_FONDO = colors.HexColor("#fbe9e9")
NEUTRO_FONDO = colors.HexColor("#eeeeec")
HEX_BARRA_OK = "#2a78d6"
HEX_BARRA_KO = "#d03b3b"

# Estilos
E = {
    "titulo": ParagraphStyle("titulo", fontName=FB, fontSize=20, leading=25, textColor=PRIMARIO, spaceAfter=4),
    "subtitulo": ParagraphStyle("subtitulo", fontName=F, fontSize=9.5, leading=13, textColor=TINTA_2),
    "h1": ParagraphStyle("h1", fontName=FB, fontSize=14, leading=18, textColor=PRIMARIO, spaceBefore=14, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName=FB, fontSize=11, leading=14, textColor=TINTA, spaceBefore=10, spaceAfter=5),
    "cuerpo": ParagraphStyle("cuerpo", fontName=F, fontSize=9.5, leading=13.5, textColor=TINTA, spaceAfter=4),
    "nota": ParagraphStyle("nota", fontName=FI, fontSize=8, leading=11, textColor=TINTA_2, spaceBefore=2, spaceAfter=4),
    "celda": ParagraphStyle("celda", fontName=F, fontSize=8.5, leading=11, textColor=TINTA),
    "celda_b": ParagraphStyle("celda_b", fontName=FB, fontSize=8.5, leading=11, textColor=TINTA),
    "celda_c": ParagraphStyle("celda_c", fontName=F, fontSize=8.5, leading=11, textColor=TINTA, alignment=TA_CENTER),
    "cab": ParagraphStyle("cab", fontName=FB, fontSize=8.5, leading=11, textColor=colors.white),
    "cab_c": ParagraphStyle("cab_c", fontName=FB, fontSize=8.5, leading=11, textColor=colors.white, alignment=TA_CENTER),
    "cita": ParagraphStyle("cita", fontName=FI, fontSize=8.5, leading=11.5, textColor=TINTA_2),
    "kpi_valor": ParagraphStyle("kpi_valor", fontName=FB, fontSize=17, leading=21, textColor=PRIMARIO, alignment=TA_CENTER),
    "kpi_texto": ParagraphStyle("kpi_texto", fontName=F, fontSize=8, leading=10, textColor=TINTA_2, alignment=TA_CENTER),
}

ANCHO = A4[0] - 4 * cm


def P(texto, estilo="cuerpo"):
    return Paragraph(texto, E[estilo])


def esc(texto) -> str:
    return escape(str(texto))


def cita(texto: str) -> str:
    return f"«{esc(texto)}»"


def _estilo_tabla(cabecera=True, zebra=True):
    cmds = [
        ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if cabecera:
        cmds.append(("BACKGROUND", (0, 0), (-1, 0), PRIMARIO))
    return cmds


def _celda_nivel(nivel: str):
    color = {"Satisfactorio": OK, "No satisfactorio": KO}.get(nivel, TINTA_2)
    estilo = ParagraphStyle("niv", parent=E["celda_c"], fontName=FB, textColor=color)
    return Paragraph(esc(nivel), estilo)


def _fondo_nivel(nivel: str):
    return {"Satisfactorio": OK_FONDO, "No satisfactorio": KO_FONDO}.get(nivel, NEUTRO_FONDO)


# --------------------------------------------------------------------------
# Gráfico
# --------------------------------------------------------------------------
def grafico_apartados(informe: Informe) -> io.BytesIO:
    datos = [(f"{a.clave}. {a.titulo}", float(a.media), a.nivel) for a in informe.apartados if a.media is not None]
    datos.reverse()
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})
    fig, ax = plt.subplots(figsize=(7.2, 0.36 * len(datos) + 0.9), dpi=200)
    etiquetas = [d[0] for d in datos]
    valores = [d[1] for d in datos]
    colores = [HEX_BARRA_OK if d[2] == "Satisfactorio" else HEX_BARRA_KO for d in datos]
    barras = ax.barh(etiquetas, valores, color=colores, height=0.58, edgecolor="#fcfcfb", linewidth=1)
    for barra, d in zip(barras, datos):
        if d[2] != "Satisfactorio":
            barra.set_hatch("////")
            barra.set_edgecolor("white")
    for i, v in enumerate(valores):
        ax.text(v + 0.04, i, fmt(v), va="center", fontsize=7.5, color="#1f2933")
    ax.axvline(3, color="#52514e", linestyle=(0, (4, 3)), linewidth=0.9)
    ax.text(3.02, len(datos) - 0.35, "Umbral satisfactorio (3,00)", fontsize=7, color="#52514e", va="bottom")
    ax.set_xlim(1, 4.35)
    ax.set_ylim(-0.6, len(datos) - 0.05)
    ax.set_xticks([1, 2, 3, 4])
    ax.set_xticklabels(["1", "2", "3", "4"])
    ax.tick_params(axis="both", length=0, colors="#52514e")
    ax.tick_params(axis="y", colors="#1f2933")
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color("#d5d9de")
    ax.grid(axis="x", color="#e6e8eb", linewidth=0.6)
    ax.set_axisbelow(True)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=HEX_BARRA_OK, label="Satisfactorio (≥ 3,00)"),
                       Patch(facecolor=HEX_BARRA_KO, hatch="////", edgecolor="white", label="No satisfactorio (< 3,00)")],
              loc="lower center", bbox_to_anchor=(0.4, 1.0), ncol=2, frameon=False, fontsize=7.5)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


# --------------------------------------------------------------------------
# Secciones
# --------------------------------------------------------------------------
def _seccion_ficha(inf: Informe):
    f = inf.ficha
    filas = [
        ["Nombre del curso", f.curso],
        ["Sociedad bonificada (Nº expediente)", f"{f.expediente}" + (f"  ·  {f.acceso}" if f.acceso else "")],
        ["Nº acción formativa / Grupo", f"{f.num_aaff} / {f.num_grupo}"],
        ["Modalidad", f.modalidad],
        ["Nº cuestionarios cumplimentados", str(f.num_cuestionarios)],
    ]
    t = Table([[P(esc(a), "celda_b"), P(esc(b), "celda")] for a, b in filas], colWidths=[6.2 * cm, ANCHO - 6.2 * cm])
    t.setStyle(TableStyle(_estilo_tabla(cabecera=False) + [("BACKGROUND", (0, 0), (0, -1), PRIMARIO_CLARO)]))
    out = [P("1. Ficha del curso", "h1"), t]
    for aviso in f.avisos:
        out.append(P("Aviso: " + esc(aviso), "nota"))
    return out


def _seccion_cuantitativa(inf: Informe):
    out = [P("2. Análisis cuantitativo", "h1"),
           P("Puntuación media de cada apartado principal del bloque III del cuestionario (escala de 1 a 4). "
             "La media de cada apartado es la media de las puntuaciones medias de sus sub-ítems; las respuestas "
             "«No contesta» no se tienen en cuenta. Nivel: entre 1,00 y 2,99 «No satisfactorio»; entre 3,00 y 4,00 "
             "«Satisfactorio». Las cifras se muestran sin redondear (truncadas a dos decimales).")]
    filas = [[P("Apartado principal", "cab"), P("Puntuación media", "cab_c"), P("Nivel de satisfacción", "cab_c")]]
    estilo = _estilo_tabla()
    for i, a in enumerate(inf.apartados, start=1):
        filas.append([P(f"{a.clave}. {esc(a.titulo)}", "celda"), P(fmt(a.media), "celda_c"), _celda_nivel(a.nivel)])
        estilo.append(("BACKGROUND", (2, i), (2, i), _fondo_nivel(a.nivel)))
        if i % 2 == 0:
            estilo.append(("BACKGROUND", (0, i), (1, i), FONDO_ALT))
    t = Table(filas, colWidths=[ANCHO - 7.4 * cm, 3.4 * cm, 4 * cm], repeatRows=1)
    t.setStyle(TableStyle(estilo))
    out += [t, Spacer(1, 10)]
    if any(a.media is not None for a in inf.apartados):
        img = grafico_apartados(inf)
        n = sum(1 for a in inf.apartados if a.media is not None)
        alto = (0.36 * n + 0.9) / 7.2 * ANCHO
        out += [KeepTogether([Image(img, width=ANCHO, height=alto)])]

    out.append(P("Detalle por apartado", "h2"))
    for a in inf.apartados:
        bloque = [P(f"2.{a.clave}. {esc(a.titulo)}", "h2")]
        if a.subitems:
            if a.tipo == "likert":
                cab = ["Sub-ítem", "N", "Media", "1", "2", "3", "4"]
                anchos = [ANCHO - 8.6 * cm, 1.2 * cm, 1.8 * cm] + [1.4 * cm] * 4
            else:
                cab = ["Sub-ítem", "N", "Media", "Sí", "No", "% Sí"]
                anchos = [ANCHO - 8.6 * cm, 1.2 * cm, 1.8 * cm, 1.6 * cm, 1.6 * cm, 2.4 * cm]
            filas = [[P(cab[0], "cab")] + [P(c, "cab_c") for c in cab[1:]]]
            for s in a.subitems:
                fila = [P(f"{esc(s.codigo)} {esc(s.texto)}", "celda"), P(str(s.n), "celda_c"), P(fmt(s.media), "celda_c")]
                if a.tipo == "likert":
                    fila += [P(str(s.distribucion[v]), "celda_c") for v in (1, 2, 3, 4)]
                else:
                    fila += [P(str(s.distribucion["Sí"]), "celda_c"), P(str(s.distribucion["No"]), "celda_c"),
                             P(fmt_pct(s.pct_si), "celda_c")]
                filas.append(fila)
            ultima = [P("Media del apartado", "celda_b"), P("", "celda_c"),
                      Paragraph(fmt(a.media), ParagraphStyle("m", parent=E["celda_c"], fontName=FB)),
                      _celda_nivel(a.nivel)] + [P("", "celda")] * (len(cab) - 4)
            filas.append(ultima)
            t = Table(filas, colWidths=anchos)
            st = _estilo_tabla() + [
                ("SPAN", (3, -1), (-1, -1)),
                ("BACKGROUND", (0, -1), (2, -1), PRIMARIO_CLARO),
                ("BACKGROUND", (3, -1), (-1, -1), _fondo_nivel(a.nivel)),
            ]
            t.setStyle(TableStyle(st))
            bloque.append(t)
            if a.tipo == "likert":
                bloque.append(P("Columnas 1-4: número de respuestas con cada puntuación "
                                "(1 Completamente en desacuerdo · 2 En desacuerdo · 3 De acuerdo · 4 Completamente de acuerdo).", "nota"))
        else:
            bloque.append(P("<b>No aplica.</b>", "cuerpo"))
        if a.nota:
            bloque.append(P(esc(a.nota), "nota"))
        out.append(KeepTogether(bloque))
    return out


def _seccion_comentarios(inf: Informe):
    com = inf.comentarios
    out = [P("3. Análisis de comentarios", "h1"),
           P(f"Comentarios del ítem 11 (sugerencias y observaciones): <b>{com.participantes_con_comentario}</b> de "
             f"<b>{com.total_participantes}</b> participantes han escrito algún comentario. Cada comentario se ha "
             f"dividido en ideas y cada idea se ha asignado al elemento del curso que valora. La frecuencia indica "
             f"cuántos participantes distintos mencionan el elemento con ese valor.")]
    if not com.elementos:
        out.append(P("No hay comentarios que analizar.", "cuerpo"))
        return out
    color_valor = {"Positivo": OK, "Negativo": KO, "Neutro": TINTA_2}
    fondo_valor = {"Positivo": OK_FONDO, "Negativo": KO_FONDO, "Neutro": NEUTRO_FONDO}
    filas = [[P("Elemento valorado", "cab"), P("Valor", "cab_c"), P("Frecuencia", "cab_c"),
              P("Comentarios ilustrativos", "cab")]]
    estilo = _estilo_tabla()
    for i, e in enumerate(com.elementos, start=1):
        ejemplos = "<br/>".join("• " + cita(x) for x in e.ejemplos) or "–"
        valor = Paragraph(esc(e.valor), ParagraphStyle("v", parent=E["celda_c"], fontName=FB, textColor=color_valor[e.valor]))
        filas.append([P(esc(e.elemento), "celda_b"), valor, P(str(e.frecuencia), "celda_c"), P(ejemplos, "cita")])
        estilo.append(("BACKGROUND", (1, i), (1, i), fondo_valor[e.valor]))
    t = Table(filas, colWidths=[4 * cm, 2.1 * cm, 2.3 * cm, ANCHO - 8.4 * cm], repeatRows=1)
    t.setStyle(TableStyle(estilo))
    out.append(t)
    return out


def _bullets(items, estilo="cuerpo"):
    return ListFlowable(
        [ListItem(P(esc(x) if estilo == "cuerpo" else x, estilo), leftIndent=12, value="•") for x in items],
        bulletType="bullet", start="•", leftIndent=12, bulletFontSize=8, bulletColor=PRIMARIO,
    )


def _citas(items):
    if not items:
        return [P("No se han registrado comentarios de los participantes sobre este punto.", "nota")]
    filas = [[P(cita(x), "cita")] for x in items]
    t = Table(filas, colWidths=[ANCHO - 0.6 * cm])
    t.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, -1), 2, PRIMARIO),
        ("BACKGROUND", (0, 0), (-1, -1), FONDO_ALT),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [Spacer(1, 3), P("Comentarios de los alumnos:", "nota"), t]


def _seccion_conclusiones(inf: Informe):
    c = inf.conclusiones
    out = [P("4. Conclusiones y recomendaciones", "h1")]

    kpis = [
        (f"{fmt(c.valoracion_global, 1)} / 10", "Valoración global del curso"),
        (esc(c.nivel_general), "Nivel de satisfacción general"),
        (fmt_pct(c.pct_satisfechos), "Participantes satisfechos (ítem 10 ≥ 3)"),
        (fmt_pct(c.pct_recomienda), "Recomendaría el curso (10.1)"),
    ]
    celdas = []
    for valor, texto in kpis:
        est = E["kpi_valor"]
        if valor in ("Satisfactorio", "No satisfactorio"):
            est = ParagraphStyle("k", parent=est, fontSize=12.5, leading=21,
                                 textColor=OK if valor == "Satisfactorio" else KO)
        celdas.append([Paragraph(valor, est), P(texto, "kpi_texto")])
    t = Table([celdas], colWidths=[ANCHO / 4] * 4)
    t.setStyle(TableStyle([
        ("BOX", (i, 0), (i, 0), 0.6, BORDE) for i in range(4)
    ] + [("BACKGROUND", (0, 0), (-1, -1), PRIMARIO_CLARO), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
         ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    out += [t, P("Valoración global = media de los apartados valorados en escala 1-4 (excepto el 8, de respuesta Sí/No), "
                 "convertida a escala 0-10 mediante (media − 1) / 3 × 10.", "nota")]

    out += [P("Resumen ejecutivo", "h2"), P(esc(c.resumen))]
    out += [P("Nivel de satisfacción general", "h2"),
            P(f"<b>{esc(c.nivel_general)}</b> — puntuación media global de {fmt(c.media_global)} sobre 4.")]

    out += [P("Principales fortalezas", "h2"), _bullets(c.fortalezas or ["No se han identificado fortalezas destacadas."])]
    out += _citas(c.comentarios_fortalezas)
    out += [P("Principales áreas de mejora", "h2"), _bullets(c.areas_mejora)]
    out += _citas(c.comentarios_mejora)

    out += [CondPageBreak(5 * cm), P("Recomendaciones de ajustes", "h2")]
    if not c.recomendaciones:
        out.append(P("No se han detectado puntos de mejora que requieran ajustes.", "cuerpo"))
    else:
        filas = [[P("Punto de mejora", "cab"), P("Comentario de un alumno", "cab"), P("Acción recomendada", "cab")]]
        for r in c.recomendaciones:
            titulo = f"<b>{esc(r.titulo)}</b>" + (f"<br/><font size=7.5 color='#52514e'>{esc(r.origen)}</font>" if r.origen else "")
            comentario = cita(r.comentario) if r.comentario else "<font color='#52514e'>Sin comentarios específicos de los alumnos.</font>"
            filas.append([P(titulo, "celda"), P(comentario, "cita"), P(esc(r.accion), "celda")])
        t = Table(filas, colWidths=[4.2 * cm, (ANCHO - 4.2 * cm) * 0.45, (ANCHO - 4.2 * cm) * 0.55], repeatRows=1)
        st = _estilo_tabla() + [("VALIGN", (0, 1), (-1, -1), "TOP")]
        for i in range(2, len(filas), 2):
            st.append(("BACKGROUND", (0, i), (-1, i), FONDO_ALT))
        t.setStyle(TableStyle(st))
        out.append(t)
    return out


def _anexo(inf: Informe, archivos: list[str], errores: list):
    out = [CondPageBreak(6 * cm), P("Anexo. Cuestionarios procesados", "h1"),
           P(f"Se han procesado correctamente {len(archivos)} archivo(s). Análisis cualitativo realizado mediante: "
             f"{'motor de reglas (diccionario de elementos y léxico de opinión)' if inf.motor == 'reglas' else esc(inf.motor)}.", "cuerpo")]
    if archivos:
        out.append(P(esc(", ".join(os.path.basename(a) for a in archivos)), "nota"))
    if errores:
        out.append(P("Archivos no procesados:", "cuerpo"))
        out.append(_bullets([f"{os.path.basename(n)}: {m}" for n, m in errores]))
    return out


# --------------------------------------------------------------------------
def generar_pdf(inf: Informe, archivos: list[str] | None = None, errores: list | None = None) -> bytes:
    buf = io.BytesIO()
    titulo = f"Informe Curso – {inf.ficha.curso}"
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=1.8 * cm, title=titulo,
                            author="Técnico de formación", subject="Evaluación de la calidad de la acción formativa")

    def pie(canvas, doc_):
        canvas.saveState()
        canvas.setStrokeColor(BORDE)
        canvas.line(2 * cm, 1.3 * cm, A4[0] - 2 * cm, 1.3 * cm)
        canvas.setFont(F, 7.5)
        canvas.setFillColor(TINTA_2)
        texto = titulo if len(titulo) < 95 else titulo[:92] + "…"
        canvas.drawString(2 * cm, 0.9 * cm, texto)
        canvas.drawRightString(A4[0] - 2 * cm, 0.9 * cm, f"Página {doc_.page}")
        canvas.restoreState()

    historia = [
        P(esc(titulo), "titulo"),
        P(f"Evaluación de la calidad de la acción formativa · {inf.ficha.num_cuestionarios} cuestionarios analizados · "
          f"generado el {date.today().strftime('%d/%m/%Y')}", "subtitulo"),
        Spacer(1, 6),
    ]
    historia += _seccion_ficha(inf)
    historia += _seccion_cuantitativa(inf)
    historia += [CondPageBreak(9 * cm)]
    historia += _seccion_comentarios(inf)
    historia += _seccion_conclusiones(inf)
    historia += _anexo(inf, archivos or [], errores or [])
    doc.build(historia, onFirstPage=pie, onLaterPages=pie)
    return buf.getvalue()


def nombre_archivo(inf: Informe) -> str:
    """«Informe Curso – <nombre>.pdf», sin caracteres no válidos en nombres de archivo."""
    import re
    curso = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", inf.ficha.curso).strip()
    curso = re.sub(r"\s+", " ", curso)[:120] or "curso"
    return f"Informe Curso – {curso}.pdf"
