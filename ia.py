"""
Mejora opcional con IA (API de Anthropic / Claude).

Si se configura una clave de API, la IA sustituye al motor de reglas en la
parte cualitativa del informe: clasificación de comentarios, resumen
ejecutivo, fortalezas, áreas de mejora y recomendaciones.
Las cifras (medias, niveles, valoración global) se calculan SIEMPRE en
código y la IA solo las recibe como contexto.
Cualquier cita de alumnos que devuelva la IA se valida contra los comentarios
originales; si no aparece literalmente, se descarta.
"""
from __future__ import annotations

import json
import re

import comentarios as cm
from analisis import Informe, PuntoMejora, fmt, fmt_pct

MODELO_POR_DEFECTO = "claude-sonnet-5-5"

INSTRUCCIONES = """Eres un técnico de formación experto en evaluación de la calidad de acciones formativas \
(cuestionarios SEPE/FUNDAE). Recibirás los resultados cuantitativos ya calculados de un curso y los comentarios \
abiertos de los participantes (ítem 11). Devuelve EXCLUSIVAMENTE un objeto JSON válido, sin texto adicional, con esta estructura:

{
  "comentarios": [
    {"elemento": "nombre corto del aspecto valorado (p. ej. Formador/a, Duración del curso, Contenidos, Materiales...)",
     "valor": "Positivo" | "Negativo" | "Neutro",
     "frecuencia": número de participantes distintos que lo mencionan,
     "ejemplos": ["cita literal 1", "cita literal 2"]}
  ],
  "resumen_ejecutivo": "entre 5 y 8 líneas (unas 90-140 palabras)",
  "fortalezas": ["fortaleza 1", "..."],
  "comentarios_fortalezas": ["cita literal", "cita literal"],
  "areas_mejora": ["área 1", "..."],
  "comentarios_mejora": ["cita literal", "cita literal"],
  "recomendaciones": [
    {"punto": "punto de mejora", "comentario": "cita literal que lo demuestra (o cadena vacía si no hay)",
     "accion": "una acción concreta y realista para corregirlo"}
  ]
}

Reglas:
- Las citas deben copiarse LITERALMENTE de los comentarios (puedes recortar a una frase completa, sin cambiar palabras).
- Cada participante cuenta una sola vez por elemento y valor.
- Basa fortalezas y áreas de mejora tanto en las puntuaciones como en los comentarios. Un apartado con media < 3 es "No satisfactorio".
- No inventes cifras: usa solo las proporcionadas.
- Escribe en español de España, con tono profesional y conciso."""


def _contexto(informe: Informe, observaciones: list[str]) -> str:
    c = informe.conclusiones
    lineas = [f"Curso: {informe.ficha.curso}", f"Nº cuestionarios: {informe.ficha.num_cuestionarios}",
              f"Modalidad: {informe.ficha.modalidad}",
              f"Valoración global: {fmt(c.valoracion_global, 1)}/10 (media {fmt(c.media_global)}/4) – {c.nivel_general}",
              f"% satisfechos (ítem 10 >= 3): {fmt_pct(c.pct_satisfechos)}; % recomendaría: {fmt_pct(c.pct_recomienda)}",
              "", "Puntuaciones por apartado (escala 1-4):"]
    for a in informe.apartados:
        lineas.append(f"- {a.clave}. {a.titulo}: {fmt(a.media)} ({a.nivel})")
        for s in a.subitems:
            lineas.append(f"    · {s.codigo} {s.texto}: {fmt(s.media)} (n={s.n})")
    lineas += ["", "Comentarios de los participantes (uno por cuestionario):"]
    for i, obs in enumerate(observaciones, 1):
        if obs.strip():
            lineas.append(f"[P{i}] {obs.strip()}")
    return "\n".join(lineas)


def _extraer_json(texto: str) -> dict:
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?|```$", "", texto, flags=re.MULTILINE).strip()
    inicio, fin = texto.find("{"), texto.rfind("}")
    return json.loads(texto[inicio:fin + 1])


def mejorar_con_ia(informe: Informe, observaciones: list[str], api_key: str,
                   modelo: str = MODELO_POR_DEFECTO) -> Informe:
    import anthropic  # import perezoso: solo es necesario si se usa la IA

    cliente = anthropic.Anthropic(api_key=api_key)
    respuesta = cliente.messages.create(
        model=modelo,
        max_tokens=6000,
        system=INSTRUCCIONES,
        messages=[{"role": "user", "content": _contexto(informe, observaciones)}],
    )
    texto = "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text")
    datos = _extraer_json(texto)

    fuente = cm.normalizar(" ".join(observaciones))

    def cita_valida(cita: str) -> bool:
        cita_n = cm.normalizar(cita).strip(" .,-\"'«»")
        return bool(cita_n) and cita_n in fuente

    def citas(lista, n=2):
        return [c.strip() for c in (lista or []) if isinstance(c, str) and cita_valida(c)][:n]

    n_part = informe.ficha.num_cuestionarios
    elementos = []
    for e in datos.get("comentarios", []):
        valor = str(e.get("valor", "Neutro")).capitalize()
        if valor not in {"Positivo", "Negativo", "Neutro"}:
            valor = "Neutro"
        try:
            frecuencia = max(1, min(int(e.get("frecuencia", 1)), n_part))
        except (TypeError, ValueError):
            frecuencia = 1
        elementos.append(cm.ElementoValorado(str(e.get("elemento", cm.OTROS)), valor, frecuencia,
                                             citas(e.get("ejemplos"))))
    if elementos:
        elementos.sort(key=lambda x: -x.frecuencia)
        informe.comentarios.elementos = elementos

    c = informe.conclusiones
    c.resumen = datos.get("resumen_ejecutivo") or c.resumen
    c.fortalezas = datos.get("fortalezas") or c.fortalezas
    c.areas_mejora = datos.get("areas_mejora") or c.areas_mejora
    c.comentarios_fortalezas = citas(datos.get("comentarios_fortalezas")) or c.comentarios_fortalezas
    c.comentarios_mejora = citas(datos.get("comentarios_mejora")) or c.comentarios_mejora
    recs = []
    for r in datos.get("recomendaciones", []):
        com = r.get("comentario", "")
        recs.append(PuntoMejora(titulo=r.get("punto", ""), origen="",
                                comentario=com if com and cita_valida(com) else "",
                                accion=r.get("accion", "")))
    if recs:
        c.recomendaciones = recs
    informe.motor = f"IA ({modelo})"
    return informe
