"""
Análisis de los comentarios abiertos (ítem 11 del apartado III).

Motor basado en reglas, sin dependencias externas:
  1. Divide cada observación en fragmentos (frases, viñetas, «pero», «aunque»...).
  2. Asigna cada fragmento al elemento del curso del que habla (diccionario de
     palabras clave con pesos).
  3. Determina el valor (positivo / negativo / neutro) con un léxico de
     opinión que tiene en cuenta negaciones sencillas («no ha sido útil»).
  4. Agrupa por elemento y valor, cuenta cuántos participantes lo mencionan y
     selecciona comentarios representativos.

Los diccionarios están en este fichero para que se puedan ampliar fácilmente.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", texto).strip()


# --------------------------------------------------------------------------
# Elementos valorados: nombre -> {palabra o expresión clave: peso}
# (sin tildes; se comparan contra el texto normalizado, por inicio de palabra)
# --------------------------------------------------------------------------
ELEMENTOS: dict[str, dict[str, int]] = {
    "Formador/a y tutorización": {
        "profesor": 2, "profesora": 2, "profe": 2, "formador": 2, "formadora": 2,
        "docente": 2, "ponente": 2, "instructor": 2, "tutor": 2, "tutora": 2,
        "explica": 1, "explicacion": 1, "dudas": 1, "domina": 1, "imparte": 1,
        "impartido": 1, "cercan": 1, "paciencia": 1,
    },
    "Duración del curso": {
        "duracion": 2, "tiempo": 1, "horas": 1, "corto": 1, "corta": 1,
        "intensivo": 1, "prisa": 2, "deprisa": 2, "rapido": 1, "dias": 1,
        "faltado tiempo": 3, "falta de tiempo": 3, "falta tiempo": 3,
        "no ha dado tiempo": 3, "no dio tiempo": 3, "mas horas": 3, "mas dias": 3,
        "mas tiempo": 3, "poco tiempo": 3, "muy corto": 3, "se queda corto": 3,
        "largo": 1, "se hace largo": 3,
    },
    "Contenidos y temario": {
        "contenido": 2, "temario": 2, "temas": 1, "tema": 1, "materia": 1,
        "programa": 1, "nivel": 1, "basico": 1, "avanzado": 1, "actualizado": 1,
        "conceptos": 1, "teoria": 1, "teorico": 1, "denso": 1,
    },
    "Metodología y enfoque práctico": {
        "practic": 2, "ejemplo": 2, "ejercicio": 2, "casos": 2, "caso practico": 3,
        "dinamica": 2, "dinamico": 2, "metodologia": 2, "participativ": 2,
        "role play": 2, "talleres": 1, "simulacion": 2, "ameno": 1, "amena": 1,
        "aburrido": 1, "monotono": 1,
    },
    "Organización y coordinación": {
        "organizacion": 2, "organizado": 2, "desorganiz": 2, "coordinacion": 2,
        "informacion previa": 2, "convocatoria": 2, "fechas": 1, "aviso": 1,
        "planificacion": 2, "gestion": 1, "comunicacion": 1, "puntualidad": 2,
        "retraso": 1,
    },
    "Horario": {
        "horario": 3, "por la tarde": 2, "por la manana": 2, "jornada": 1,
        "fuera de horario": 3, "viernes": 1, "descansos": 2, "pausas": 2,
    },
    "Materiales y documentación": {
        "material": 2, "documentacion": 2, "manual": 2, "apuntes": 2,
        "presentaciones": 2, "diapositivas": 2, "transparencias": 2, "guia": 1,
        "bibliografia": 2, "recursos": 1, "plantillas": 2,
    },
    "Instalaciones": {
        "aula": 2, "sala": 2, "instalaciones": 3, "sillas": 2, "mesas": 2,
        "climatizacion": 2, "aire acondicionado": 2, "calefaccion": 2, "frio": 1,
        "calor": 1, "espacio": 1, "ruido": 2, "luz": 1, "aparcamiento": 2,
        "ubicacion": 1, "cafe": 1,
    },
    "Medios técnicos": {
        "proyector": 2, "ordenador": 2, "pantalla": 2, "wifi": 2, "internet": 2,
        "equipos": 2, "portatil": 2, "software": 2, "medios tecnicos": 3,
        "microfono": 2, "sonido": 1, "licencia": 1,
    },
    "Plataforma y formación online": {
        "plataforma": 3, "campus": 2, "online": 2, "on line": 2, "virtual": 2,
        "teams": 2, "zoom": 2, "videoconferencia": 2, "conexion": 1,
        "teleformacion": 2, "grabacion": 2, "grabaciones": 2,
    },
    "Evaluación y acreditación": {
        "examen": 2, "evaluacion": 2, "test": 2, "autoevaluacion": 2,
        "certificado": 2, "certificacion": 2, "diploma": 2, "acreditacion": 2,
        "titulo": 1,
    },
    "Utilidad y aplicabilidad": {
        "util": 2, "utilidad": 2, "aplicar": 2, "aplicable": 2, "aplicacion": 1,
        "dia a dia": 2, "puesto": 1, "trabajo": 1, "provecho": 2, "aprendido": 1,
        "aprendizaje": 1, "interesante": 1, "recomendable": 1, "recomiendo": 1,
    },
    "Grupo y participantes": {
        "grupo": 2, "companeros": 2, "alumnos": 1, "participantes": 2,
        "heterogeneo": 2, "numero de alumnos": 3, "networking": 2,
    },
}
OTROS = "Otros aspectos"

# --------------------------------------------------------------------------
# Léxico de opinión (sin tildes)
# --------------------------------------------------------------------------
POSITIVAS = {
    "excelente", "excelentes", "estupendo", "estupenda", "genial", "perfecto",
    "perfecta", "magnifico", "magnifica", "fantastico", "fantastica", "bueno",
    "buena", "buenos", "buenas", "buen", "bien", "claro", "clara", "claros",
    "claridad", "util", "utiles", "interesante", "interesantes", "ameno", "amena",
    "dinamico", "dinamica", "practico", "practica", "practicos", "recomendable",
    "recomiendo", "encantado", "encantada", "encanto", "gusto", "gustado",
    "satisfecho", "satisfecha", "agradable", "agradecer", "gracias", "enhorabuena",
    "domina", "dominio", "cercano", "cercana", "paciencia", "atento", "atenta",
    "resuelto", "resuelve", "adecuado", "adecuada", "adecuados", "completo",
    "completa", "organizado", "organizada", "actualizado", "actualizados",
    "aprendido", "provechoso", "enriquecedor", "motivador", "facil", "comodo",
    "comoda", "puntual", "profesional", "mejor", "top", "ejemplos",
}
NEGATIVAS = {
    "mal", "malo", "mala", "malos", "malas", "peor", "pesimo", "pesima",
    "insuficiente", "insuficientes", "escaso", "escasa", "escasos", "poco", "poca",
    "pocos", "pocas", "falta", "faltado", "faltan", "falto", "carencia", "lento",
    "lenta", "aburrido", "aburrida", "monotono", "denso", "densa", "extenso",
    "extensa", "pesado", "pesada", "repetitivo", "repetitiva", "desorganizado",
    "desorganizada", "desorganizacion", "caos", "retraso", "retrasos",
    "problema", "problemas", "fallo", "fallos", "fallaba", "incomodo", "incomoda",
    "frio", "calor", "ruido", "ruidoso", "corto", "corta", "rapido", "deprisa",
    "prisa", "confuso", "confusa", "desactualizado", "obsoleto", "obsoletos",
    "mejorable", "mejorar", "deberia", "deberian", "habria", "echo", "basico",
    "superficial", "complicado", "dificil", "dificultad", "imposible", "nada",
    "decepcion", "decepcionante", "largo", "larga", "agobio", "agobiante",
}
EXPRESIONES_NEGATIVAS = [
    "no ha dado tiempo", "no dio tiempo", "no da tiempo", "falta de", "ha faltado",
    "se queda corto", "se quedo corto", "se hace largo", "mas tiempo", "mas horas",
    "mas dias", "mas practica", "mas ejemplos", "mas casos", "poco tiempo",
    "no funcionaba", "no funciona", "no se oia", "no se veia", "echo en falta",
    "en falta", "seria conveniente", "seria mejor", "seria bueno", "habria que",
    "se podria mejorar", "a mejorar", "demasiado", "demasiada", "no me ha gustado",
    "sin embargo",
]
EXPRESIONES_POSITIVAS = [
    "muy bien", "muy bueno", "muy buena", "muy util", "muy interesante",
    "me ha gustado", "me ha encantado", "lo recomiendo", "muy recomendable",
    "todo perfecto", "todo bien", "muy completo", "muy practico",
]
NEGADORES = {"no", "nunca", "ni", "sin", "tampoco", "nada"}
# Raíces inequívocas (cubren género, número y tiempos verbales)
RAICES_POSITIVAS = (
    "excelen", "estupend", "fantastic", "magnific", "interesant", "recomend",
    "satisf", "encant", "agradec", "facilit", "favorec", "favorab", "enriquec",
    "motivad", "aprovech", "provechos", "genial", "perfect", "amen",
)
RAICES_NEGATIVAS = (
    "desactualiz", "desorganiz", "insuficien", "obsolet", "aburri", "incomod",
    "confus", "decepcion", "repetitiv", "falla", "fallo", "escas", "deficien",
    "precari", "caotic", "agobi", "estres", "desfas", "inadecuad",
)

SIN_CONTENIDO = {
    "", "-", "--", ".", "no", "nada", "ninguna", "ninguno", "ningun comentario",
    "sin comentarios", "sin observaciones", "ninguna observacion", "n/a", "na",
    "no tengo", "nada que anadir", "ninguna sugerencia",
}

SEPARADORES = re.compile(
    r"(?:\n+|;|(?<!\d)\.(?!\d)|\s+-\s+|^\s*[-•*·]\s*|\bpero\b|\baunque\b|\bsin embargo\b|\bno obstante\b)",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class Fragmento:
    texto: str
    participante: int
    elemento: str
    valor: str  # "Positivo" | "Negativo" | "Neutro"
    puntuacion: int


@dataclass
class ElementoValorado:
    elemento: str
    valor: str
    frecuencia: int  # nº de participantes que lo mencionan
    ejemplos: list = field(default_factory=list)  # hasta 2 comentarios


@dataclass
class AnalisisComentarios:
    total_participantes: int
    participantes_con_comentario: int
    fragmentos: list
    elementos: list  # list[ElementoValorado] ordenada por frecuencia

    def por_valor(self, valor: str) -> list:
        return [e for e in self.elementos if e.valor == valor]

    def ejemplos(self, valor: str, elementos: set | None = None, n: int = 2) -> list:
        """Mejores comentarios de un valor (opcionalmente de ciertos elementos)."""
        candidatos = [
            f for f in self.fragmentos
            if f.valor == valor and (elementos is None or f.elemento in elementos)
        ]
        return _seleccionar(candidatos, n)


# --------------------------------------------------------------------------
def _contiene(texto_norm: str, clave: str) -> int:
    """Nº de apariciones de la clave como inicio de palabra."""
    return len(re.findall(r"(?<![a-zñ])" + re.escape(clave), texto_norm))


def clasificar_elemento(texto_norm: str) -> str:
    puntos = {}
    for elemento, claves in ELEMENTOS.items():
        total = sum(peso for clave, peso in claves.items() if _contiene(texto_norm, clave))
        if total:
            puntos[elemento] = total
    if not puntos:
        return OTROS
    # empate -> el orden del diccionario actúa como prioridad
    return max(puntos, key=lambda e: (puntos[e], -list(ELEMENTOS).index(e)))


def puntuar_opinion(texto_norm: str) -> int:
    score = 0
    resto = texto_norm
    for exp in EXPRESIONES_NEGATIVAS:
        if exp in resto:
            score -= 2
            resto = resto.replace(exp, " ")
    for exp in EXPRESIONES_POSITIVAS:
        for m in list(re.finditer(re.escape(exp), resto)):
            previas = re.findall(r"[a-zñ]+", resto[:m.start()])[-3:]
            score += -2 if any(w in NEGADORES for w in previas) else 2
        resto = resto.replace(exp, " ")
    palabras = re.findall(r"[a-zñ]+", resto)
    for i, p in enumerate(palabras):
        negada = any(w in NEGADORES for w in palabras[max(0, i - 3):i])
        if p in POSITIVAS or p.startswith(RAICES_POSITIVAS):
            score += -1 if negada else 1
        elif (p in NEGATIVAS or p.startswith(RAICES_NEGATIVAS)) and p not in NEGADORES:
            score += 1 if negada and p not in {"falta", "faltado"} else -1
    return score


def _valor(score: int) -> str:
    if score > 0:
        return "Positivo"
    if score < 0:
        return "Negativo"
    return "Neutro"


def _limpiar_fragmento(texto: str) -> str:
    texto = re.sub(r"^[\s\-•*·,:)]+|[\s,:(\-]+$", "", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto[:1].upper() + texto[1:] if texto else texto


def dividir(observacion: str) -> list:
    partes = [_limpiar_fragmento(p) for p in SEPARADORES.split(observacion or "")]
    return [p for p in partes if p and len(normalizar(p)) > 3 and normalizar(p) not in SIN_CONTENIDO]


def _seleccionar(fragmentos: list, n: int) -> list:
    """Elige comentarios ilustrativos: de participantes distintos, con opinión
    marcada y longitud razonable."""
    ordenados = sorted(
        fragmentos,
        key=lambda f: (-abs(f.puntuacion), abs(len(f.texto) - 90), f.participante),
    )
    elegidos, vistos, participantes = [], set(), set()
    for f in ordenados:
        clave = normalizar(f.texto)
        if clave in vistos or f.participante in participantes:
            continue
        elegidos.append(f.texto)
        vistos.add(clave)
        participantes.add(f.participante)
        if len(elegidos) == n:
            break
    if len(elegidos) < n:  # completar aunque se repita participante
        for f in ordenados:
            if normalizar(f.texto) not in vistos:
                elegidos.append(f.texto)
                vistos.add(normalizar(f.texto))
                if len(elegidos) == n:
                    break
    return elegidos


def analizar(observaciones: list[str]) -> AnalisisComentarios:
    fragmentos = []
    con_comentario = 0
    for idx, obs in enumerate(observaciones):
        partes = dividir(obs)
        if partes:
            con_comentario += 1
        for parte in partes:
            norm = normalizar(parte)
            score = puntuar_opinion(norm)
            fragmentos.append(Fragmento(parte, idx, clasificar_elemento(norm), _valor(score), score))

    grupos = defaultdict(list)
    for f in fragmentos:
        grupos[(f.elemento, f.valor)].append(f)

    elementos = [
        ElementoValorado(
            elemento=el,
            valor=val,
            frecuencia=len({f.participante for f in frs}),
            ejemplos=_seleccionar(frs, 2),
        )
        for (el, val), frs in grupos.items()
    ]
    orden_valor = {"Positivo": 0, "Negativo": 1, "Neutro": 2}
    elementos.sort(key=lambda e: (-e.frecuencia, orden_valor[e.valor], e.elemento == OTROS, e.elemento))
    return AnalisisComentarios(len(observaciones), con_comentario, fragmentos, elementos)
