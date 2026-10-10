"""
Cálculos del informe: ficha del curso, análisis cuantitativo, conclusiones
y recomendaciones.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal
from fractions import Fraction

import comentarios as cm
from extractor import APARTADOS, Cuestionario

UMBRAL_SATISFACTORIO = Fraction(3)
MODALIDADES_TELE = {"Teleformacion", "Teleformación", "Mixta"}


# --------------------------------------------------------------------------
# Utilidades de formato
# --------------------------------------------------------------------------
def nivel(media) -> str:
    if media is None:
        return "No aplica"
    return "Satisfactorio" if media >= UMBRAL_SATISFACTORIO else "No satisfactorio"


def fmt(valor, decimales: int = 2) -> str:
    """Muestra el valor SIN redondear (se trunca), con coma decimal.
    Así 2,999 se muestra como 2,99 y nunca aparenta un nivel distinto al real."""
    if valor is None:
        return "–"
    d = Decimal(valor.numerator) / Decimal(valor.denominator) if isinstance(valor, Fraction) else Decimal(str(valor))
    d = d.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_DOWN)
    return f"{d:.{decimales}f}".replace(".", ",")


def fmt_pct(valor) -> str:
    return "–" if valor is None else f"{fmt(valor * 100, 1)} %"


def _media(valores):
    valores = [v for v in valores if v is not None]
    return Fraction(sum(valores), len(valores)) if valores else None


# --------------------------------------------------------------------------
# Estructuras de resultado
# --------------------------------------------------------------------------
@dataclass
class SubItem:
    codigo: str
    texto: str
    n: int
    media: Fraction | None
    distribucion: dict  # valor -> nº respuestas
    pct_si: Fraction | None = None


@dataclass
class Apartado:
    clave: str
    titulo: str
    tipo: str
    media: Fraction | None
    nivel: str
    subitems: list
    nota: str = ""


@dataclass
class FichaCurso:
    curso: str
    expediente: str
    acceso: str
    cif: str
    num_aaff: str
    num_grupo: str
    modalidad: str
    num_cuestionarios: int
    avisos: list = field(default_factory=list)


@dataclass
class PuntoMejora:
    titulo: str
    origen: str
    comentario: str
    accion: str


@dataclass
class Conclusiones:
    valoracion_global: Fraction | None  # 0-10
    media_global: Fraction | None  # 1-4
    nivel_general: str
    pct_satisfechos: Fraction | None
    pct_recomienda: Fraction | None
    resumen: str
    fortalezas: list  # textos
    comentarios_fortalezas: list
    areas_mejora: list
    comentarios_mejora: list
    recomendaciones: list  # list[PuntoMejora]


@dataclass
class Informe:
    ficha: FichaCurso
    apartados: list
    comentarios: cm.AnalisisComentarios
    conclusiones: Conclusiones
    motor: str = "reglas"


# --------------------------------------------------------------------------
def _mas_comun(valores) -> str:
    valores = [v for v in valores if v]
    return Counter(valores).most_common(1)[0][0] if valores else "–"


def ficha_curso(cuestionarios: list[Cuestionario]) -> FichaCurso:
    ficha = FichaCurso(
        curso=_mas_comun(c.curso for c in cuestionarios),
        expediente=_mas_comun(c.expediente for c in cuestionarios),
        acceso=_mas_comun(c.acceso for c in cuestionarios),
        cif=_mas_comun(c.cif for c in cuestionarios),
        num_aaff=_mas_comun(c.num_aaff for c in cuestionarios),
        num_grupo=_mas_comun(c.num_grupo for c in cuestionarios),
        modalidad=_mas_comun(c.modalidad for c in cuestionarios).replace("Teleformacion", "Teleformación"),
        num_cuestionarios=len(cuestionarios),
    )
    for etiqueta, attr in [("Nº expediente", "expediente"), ("Nº AAFF", "num_aaff"), ("Nº grupo", "num_grupo")]:
        distintos = {getattr(c, attr) for c in cuestionarios if getattr(c, attr)}
        if len(distintos) > 1:
            ficha.avisos.append(f"Se han encontrado varios valores de {etiqueta}: {', '.join(sorted(distintos))}.")
    return ficha


def analisis_cuantitativo(cuestionarios: list[Cuestionario], incluir_tele_siempre: bool = False) -> list[Apartado]:
    resultado = []
    for clave, titulo, tipo, items in APARTADOS:
        muestra = cuestionarios
        nota = ""
        if clave == "7" and not incluir_tele_siempre:
            muestra = [c for c in cuestionarios if c.modalidad in MODALIDADES_TELE]
            if not muestra:
                resultado.append(Apartado(clave, titulo, tipo, None, "No aplica", [],
                                          "Curso impartido en modalidad presencial: el apartado 7 solo se "
                                          "valora en teleformación o modalidad mixta."))
                continue
            nota = f"Calculado sobre los {len(muestra)} cuestionarios de modalidad teleformación o mixta."

        subitems = []
        for codigo, texto, campo in items:
            respuestas = [c.respuestas.get(campo) for c in muestra]
            validas = [r for r in respuestas if r is not None]
            if tipo == "likert":
                dist = {v: validas.count(v) for v in (1, 2, 3, 4)}
                subitems.append(SubItem(codigo, texto, len(validas), _media(validas), dist))
            else:  # Sí / No  ->  Sí = 4, No = 1 (equivalencia en la escala 1-4)
                si = sum(1 for r in validas if r)
                dist = {"Sí": si, "No": len(validas) - si}
                pct = Fraction(si, len(validas)) if validas else None
                media = _media([4 if r else 1 for r in validas])
                subitems.append(SubItem(codigo, texto, len(validas), media, dist, pct))

        if tipo == "si_no":
            nota = "Ítems de respuesta Sí/No: para obtener la puntuación se aplica la equivalencia Sí = 4 y No = 1."
        if clave == "10":
            rec = [c.recomienda for c in muestra if c.recomienda is not None]
            if rec:
                nota = (f"Además, el {fmt_pct(Fraction(sum(rec), len(rec)))} de quienes responden "
                        f"recomendaría el curso (10.1; {len(rec)} respuestas).")
            else:
                nota = "Ningún participante ha respondido a la pregunta 10.1 (¿Recomendaría este curso?)."

        media = _media([s.media for s in subitems])  # media de las medias de los sub-ítems
        resultado.append(Apartado(clave, titulo, tipo, media, nivel(media), subitems, nota))
    return resultado


# --------------------------------------------------------------------------
# Conclusiones y recomendaciones (motor de reglas)
# --------------------------------------------------------------------------
# Relación apartado del cuestionario -> elementos de los comentarios
APARTADO_A_ELEMENTOS = {
    "1": {"Organización y coordinación", "Grupo y participantes"},
    "2": {"Contenidos y temario", "Metodología y enfoque práctico"},
    "3": {"Duración del curso", "Horario"},
    "4": {"Formador/a y tutorización"},
    "5": {"Materiales y documentación"},
    "6": {"Instalaciones", "Medios técnicos"},
    "7": {"Plataforma y formación online"},
    "8": {"Evaluación y acreditación"},
    "9": {"Utilidad y aplicabilidad"},
    "10": set(),
}

ACCIONES = {
    "1": "Enviar con antelación la información práctica del curso (calendario, horarios, materiales) y revisar el tamaño del grupo para que permita la participación de todos.",
    "2": "Revisar el programa con el formador a partir de un diagnóstico previo de necesidades y equilibrar teoría y práctica con más casos y ejercicios aplicados.",
    "3": "Ajustar la duración a la extensión real de los objetivos (ampliar horas o priorizar contenidos) y consultar a los participantes el horario más favorable.",
    "4": "Compartir estos resultados con el equipo docente y acordar mejoras de metodología; valorar observación de sesiones o formación de formadores.",
    "5": "Actualizar la documentación y entregar materiales de apoyo (manual, presentaciones, plantillas) antes o al inicio de cada sesión.",
    "6": "Verificar antes del curso el aula y el equipamiento (proyector, ordenadores, conexión, climatización) mediante una lista de comprobación.",
    "7": "Revisar la usabilidad de la plataforma y reforzar el soporte: guía de acceso, tutorías individualizadas y tiempos de respuesta definidos.",
    "8": "Incorporar pruebas de evaluación y autoevaluación al final de cada módulo e informar claramente al inicio sobre la acreditación que se obtiene.",
    "9": "Vincular los contenidos a situaciones reales del puesto de trabajo e incluir un plan de transferencia (acciones a aplicar tras el curso).",
    "10": "Analizar con el proveedor y el formador los aspectos peor valorados y realizar un seguimiento específico en la siguiente edición.",
}
ACCIONES_ELEMENTO = {
    "Formador/a y tutorización": ACCIONES["4"],
    "Duración del curso": "Ampliar la duración del curso o reducir y priorizar el temario para poder cubrirlo completo con el ritmo adecuado.",
    "Contenidos y temario": "Revisar el temario para ajustarlo al nivel y necesidades del grupo, priorizando los contenidos de mayor aplicación.",
    "Metodología y enfoque práctico": "Aumentar el peso de la práctica: más casos reales, ejercicios y dinámicas participativas en cada sesión.",
    "Organización y coordinación": ACCIONES["1"],
    "Horario": "Consultar a los participantes el horario preferido antes de programar y prever pausas suficientes en sesiones largas.",
    "Materiales y documentación": ACCIONES["5"],
    "Instalaciones": "Revisar el aula antes del curso (confort, climatización, espacio, ruido) o cambiar a una sala más adecuada.",
    "Medios técnicos": "Comprobar el funcionamiento de los equipos el día anterior y disponer de alternativas de respaldo (equipo y conexión).",
    "Plataforma y formación online": ACCIONES["7"],
    "Evaluación y acreditación": ACCIONES["8"],
    "Utilidad y aplicabilidad": ACCIONES["9"],
    "Grupo y participantes": "Limitar el número de participantes y formar grupos de nivel homogéneo mediante una prueba o cuestionario previo.",
    cm.OTROS: "Revisar este aspecto con el proveedor y el formador y comprobar su evolución en la siguiente edición.",
}


def _valoracion_10(media_1_4: Fraction | None):
    return None if media_1_4 is None else (media_1_4 - 1) / 3 * 10


def _lista_natural(items: list[str]) -> str:
    items = [i.lower() if i[:1].isupper() and not i[:2].isupper() else i for i in items]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]


def conclusiones(cuestionarios, apartados: list[Apartado], com: cm.AnalisisComentarios) -> Conclusiones:
    likert = [a for a in apartados if a.tipo == "likert" and a.media is not None]
    media_global = _media([a.media for a in likert])
    valoracion = _valoracion_10(media_global)

    sat = [c.respuestas.get("ID_GRADO_SATISFACCION") for c in cuestionarios]
    sat = [s for s in sat if s is not None]
    pct_sat = Fraction(sum(1 for s in sat if s >= 3), len(sat)) if sat else None
    rec = [c.recomienda for c in cuestionarios if c.recomienda is not None]
    pct_rec = Fraction(sum(rec), len(rec)) if rec else None

    evaluados = [a for a in apartados if a.media is not None]
    ordenados = sorted(evaluados, key=lambda a: a.media, reverse=True)

    # --- Fortalezas -------------------------------------------------------
    fuertes = [a for a in ordenados if a.media >= Fraction(7, 2)][:4] or \
              [a for a in ordenados if a.media >= UMBRAL_SATISFACTORIO][:2]
    fortalezas = [f"{a.titulo} (media {fmt(a.media)} sobre 4)" for a in fuertes]
    positivos = [e for e in com.por_valor("Positivo") if e.elemento != cm.OTROS]
    for e in positivos[:3]:
        fortalezas.append(f"Comentarios favorables sobre {e.elemento.lower()} "
                          f"({e.frecuencia} participante{'s' if e.frecuencia != 1 else ''})")
    elem_fuertes = {el for a in fuertes for el in APARTADO_A_ELEMENTOS.get(a.clave, set())} | {e.elemento for e in positivos}
    coment_fort = com.ejemplos("Positivo", elem_fuertes, 2) or com.ejemplos("Positivo", None, 2)

    # --- Áreas de mejora ----------------------------------------------------
    debiles = [a for a in reversed(ordenados) if a.media < UMBRAL_SATISFACTORIO]
    if not debiles:  # todo satisfactorio: se señalan los dos apartados con menor puntuación
        debiles = [a for a in reversed(ordenados) if a.media < Fraction(7, 2)][:2]
    negativos = [e for e in com.por_valor("Negativo")]
    areas = [f"{a.titulo} (media {fmt(a.media)} sobre 4 – {a.nivel.lower()})" for a in debiles]
    elementos_cubiertos = set()
    for a in debiles:
        elementos_cubiertos |= APARTADO_A_ELEMENTOS.get(a.clave, set())
    for e in negativos[:4]:
        areas.append(f"Comentarios críticos sobre {e.elemento.lower()} "
                     f"({e.frecuencia} participante{'s' if e.frecuencia != 1 else ''})")
    elem_debiles = elementos_cubiertos | {e.elemento for e in negativos}
    coment_mej = com.ejemplos("Negativo", elem_debiles, 2) or com.ejemplos("Negativo", None, 2)

    # --- Recomendaciones ------------------------------------------------------
    recomendaciones, usados = [], set()
    for a in debiles:
        elems = APARTADO_A_ELEMENTOS.get(a.clave, set())
        ejemplo = com.ejemplos("Negativo", elems, 1) if elems else []
        recomendaciones.append(PuntoMejora(
            titulo=a.titulo,
            origen=f"Puntuación media {fmt(a.media)} sobre 4 ({a.nivel.lower()})",
            comentario=ejemplo[0] if ejemplo else "",
            accion=ACCIONES[a.clave],
        ))
        usados |= elems
    for e in negativos:
        if e.elemento in usados:
            continue
        recomendaciones.append(PuntoMejora(
            titulo=e.elemento,
            origen=f"Mencionado negativamente por {e.frecuencia} participante{'s' if e.frecuencia != 1 else ''}",
            comentario=e.ejemplos[0] if e.ejemplos else "",
            accion=ACCIONES_ELEMENTO.get(e.elemento, ACCIONES_ELEMENTO[cm.OTROS]),
        ))
        usados.add(e.elemento)
        if len(recomendaciones) >= 7:
            break

    # --- Resumen ejecutivo ----------------------------------------------------
    n = len(cuestionarios)
    frases = [
        f"Se han analizado {n} cuestionario{'s' if n != 1 else ''} de evaluación de la acción formativa.",
    ]
    if valoracion is not None:
        frases.append(f"La valoración global del curso es de {fmt(valoracion, 1)} sobre 10 "
                      f"(media de {fmt(media_global)} sobre 4), con un nivel de satisfacción general "
                      f"{nivel(media_global).lower()}.")
    extra = []
    if pct_sat is not None:
        extra.append(f"el {fmt_pct(pct_sat)} de los participantes se declara satisfecho o muy satisfecho")
    if pct_rec is not None:
        extra.append(f"el {fmt_pct(pct_rec)} recomendaría el curso")
    if extra:
        frases.append(_mayus(" y ".join(extra)) + ".")
    if ordenados:
        mejores = [a.titulo for a in ordenados[:2]]
        frases.append(f"Los apartados mejor valorados son {_lista_natural(mejores)}.")
    if debiles:
        frases.append(f"Los aspectos que requieren mayor atención son {_lista_natural([a.titulo for a in debiles[:3]])}.")
    if com.participantes_con_comentario:
        temas_pos = [e.elemento for e in positivos[:2]]
        temas_neg = [e.elemento for e in negativos[:2]]
        t = f"{com.participantes_con_comentario} participantes aportan comentarios"
        if temas_pos:
            t += f", que destacan positivamente {_lista_natural(temas_pos)}"
        if temas_neg:
            t += f" y señalan como mejorable {_lista_natural(temas_neg)}"
        frases.append(t + ".")
    else:
        frases.append("Ningún participante ha incluido comentarios en el apartado de sugerencias.")
    frases.append("Se proponen a continuación ajustes concretos para las próximas ediciones.")

    return Conclusiones(
        valoracion_global=valoracion,
        media_global=media_global,
        nivel_general=nivel(media_global),
        pct_satisfechos=pct_sat,
        pct_recomienda=pct_rec,
        resumen=" ".join(frases),
        fortalezas=fortalezas,
        comentarios_fortalezas=coment_fort,
        areas_mejora=areas or ["No se han detectado áreas de mejora relevantes."],
        comentarios_mejora=coment_mej,
        recomendaciones=recomendaciones,
    )


def _mayus(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


def generar_informe(cuestionarios: list[Cuestionario], incluir_tele_siempre: bool = False) -> Informe:
    ficha = ficha_curso(cuestionarios)
    apartados = analisis_cuantitativo(cuestionarios, incluir_tele_siempre)
    com = cm.analizar([c.observaciones for c in cuestionarios])
    concl = conclusiones(cuestionarios, apartados, com)
    return Informe(ficha, apartados, com, concl)
