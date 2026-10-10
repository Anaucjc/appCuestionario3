"""
Extracción de datos de los cuestionarios SEPE / FUNDAE (PDF rellenables).

Cada cuestionario es un PDF con formulario (AcroForm). Las respuestas se leen
directamente de los campos del formulario, lo que es mucho más fiable que
interpretar el texto o la imagen de la página.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import logging

from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.ERROR)

# --------------------------------------------------------------------------
# Escalas
# --------------------------------------------------------------------------
ESCALA_LIKERT = {
    "Completamente en desacuerdo": 1,
    "En desacuerdo": 2,
    "De acuerdo": 3,
    "Completamente de acuerdo": 4,
}
ESCALA_SI_NO = {"Si": True, "Sí": True, "No": False}

# --------------------------------------------------------------------------
# Estructura del apartado III del cuestionario
# (clave, título, tipo, [(código, texto, campo PDF), ...])
# --------------------------------------------------------------------------
APARTADOS = [
    ("1", "Organización del curso", "likert", [
        ("1.1", "El curso ha estado bien organizado", "ID_BUENA_ORGANIZACION"),
        ("1.2", "El número de alumnos del grupo ha sido adecuado", "ID_NUM_ALUMNOS_ADECUADO"),
    ]),
    ("2", "Contenidos y metodología de impartición", "likert", [
        ("2.1", "Los contenidos han respondido a mis necesidades formativas", "ID_CONTENIDOS_SEGUN_NECESIDADES"),
        ("2.2", "Combinación adecuada de teoría y aplicación práctica", "ID_CONTENIDOS_SEGUN_TEORIA_PRACTICA"),
    ]),
    ("3", "Duración y horario", "likert", [
        ("3.1", "La duración ha sido suficiente", "ID_DURACION_SUFICIENTE"),
        ("3.2", "El horario ha favorecido la asistencia", "ID_HORARIO_FAVORABLE"),
    ]),
    ("4", "Formadores y tutores", "likert", [
        ("4.1F", "Formadores: la forma de impartir ha facilitado el aprendizaje", "ID_FORMADOR_FACILITADOR"),
        ("4.2F", "Formadores: conocen los temas en profundidad", "ID_FORMADOR_CONOCE_TEMA"),
        ("4.1T", "Tutores: la forma de tutorizar ha facilitado el aprendizaje", "ID_TUTOR_FACILITADOR"),
        ("4.2T", "Tutores: conocen los temas en profundidad", "ID_TUTOR_CONOCE_TEMA"),
    ]),
    ("5", "Medios didácticos", "likert", [
        ("5.1", "Documentación y materiales comprensibles y adecuados", "ID_MEDIOS_COMPRENSIBLES"),
        ("5.2", "Los medios didácticos están actualizados", "ID_MEDIOS_ACTUALIZADOS"),
    ]),
    ("6", "Instalaciones y medios técnicos", "likert", [
        ("6.1", "Aula, taller o instalaciones apropiadas", "ID_INSTALACIONES_ADECUADAS"),
        ("6.2", "Medios técnicos adecuados", "ID_MEDIOS_TECNICOS_ADECUADOS"),
    ]),
    ("7", "Modalidad telemática o mixta", "likert", [
        ("7.1", "Guías tutoriales y materiales permiten realizar el curso", "ID_TELEFORMACION_GUIA"),
        ("7.2", "Medios de apoyo suficientes", "ID_TELEFORMACION_MEDIOS"),
    ]),
    ("8", "Mecanismos para la evaluación del aprendizaje", "si_no", [
        ("8.1", "Pruebas de evaluación y autoevaluación", "ID_PRUEBAS_EVALUACION"),
        ("8.2", "Permite obtener una acreditación", "ID_ACREDITACION"),
    ]),
    ("9", "Valoración general del curso", "likert", [
        ("9.1", "Contribuye a la incorporación al mercado de trabajo", "ID_INCORPORACION_MERCADO"),
        ("9.2", "Nuevas habilidades aplicables al puesto", "Habilidades_trabajar_en_formado"),
        ("9.3", "Mejora posibilidades de cambiar de puesto", "ID_CONOCIMIENTOS_PUESTO_TRABAJO"),
        ("9.4", "Amplía conocimientos para progresar", "ID_PROGRESAR_CARRERA"),
        ("9.5", "Favorece el desarrollo personal", "ID_DESARROLLO_PERSONAL"),
    ]),
    ("10", "Grado de satisfacción general con el curso", "likert", [
        ("10", "Grado de satisfacción general", "ID_GRADO_SATISFACCION"),
    ]),
]
CAMPO_RECOMIENDA = "ID_RECOMENDARIA_CURSO"


@dataclass
class Cuestionario:
    archivo: str
    expediente: str = ""
    acceso: str = ""
    cif: str = ""
    num_aaff: str = ""
    num_grupo: str = ""
    curso: str = ""
    modalidad: str = ""
    respuestas: dict = field(default_factory=dict)  # campo -> int | bool | None
    recomienda: bool | None = None
    observaciones: str = ""


@dataclass
class ResultadoCarga:
    cuestionarios: list
    errores: list  # (archivo, motivo)


# --------------------------------------------------------------------------
def _limpiar(valor) -> str:
    if valor is None:
        return ""
    s = str(valor)
    if s.startswith("/"):
        s = s[1:]
    return s.replace("\r", "\n").strip()


def _valor_boton(campo: dict) -> str:
    """Valor de un grupo de botones de opción; si /V falta, mira el /AS de los hijos."""
    v = _limpiar(campo.get("/V"))
    if v and v != "Off":
        return v
    for kid in campo.get("/Kids", []) or []:
        try:
            kid = kid.get_object()
            estado = _limpiar(kid.get("/AS"))
            if estado and estado != "Off":
                return estado
        except Exception:  # pragma: no cover - PDF raro
            continue
    return ""


def leer_cuestionario(datos: bytes, nombre: str) -> Cuestionario:
    try:
        lector = PdfReader(io.BytesIO(datos))
        if lector.is_encrypted:
            lector.decrypt("")
        campos = lector.get_fields() or {}
    except Exception as exc:
        raise ValueError(f"no se puede leer el PDF (archivo dañado o protegido: {exc})") from exc
    if not campos:
        raise ValueError("el PDF no contiene campos de formulario rellenables")
    if "D_ACCION_FORMATIVA" not in campos and "ID_GRADO_SATISFACCION" not in campos:
        raise ValueError("no parece un cuestionario de evaluación SEPE/FUNDAE")

    def txt(nombre_campo: str) -> str:
        return _limpiar(campos.get(nombre_campo, {}).get("/V"))

    c = Cuestionario(
        archivo=nombre,
        expediente=txt("D_NUM_EXPEDIENTE"),
        acceso=txt("D_EXPEDIENTE_DM"),
        cif=txt("D_CIF"),
        num_aaff=txt("D_COD_AAFF"),
        num_grupo=txt("D_COD_GRUPO"),
        curso=" ".join(txt("D_ACCION_FORMATIVA").split()),
        modalidad=_valor_boton(campos.get("ID_MODALIDAD", {})),
        observaciones=txt("D_OBSERVACION"),
    )

    for _, _, tipo, items in APARTADOS:
        escala = ESCALA_LIKERT if tipo == "likert" else ESCALA_SI_NO
        for _, _, campo_pdf in items:
            valor = _valor_boton(campos.get(campo_pdf, {}))
            c.respuestas[campo_pdf] = escala.get(valor)  # None = No contesta / vacío

    c.recomienda = ESCALA_SI_NO.get(_valor_boton(campos.get(CAMPO_RECOMIENDA, {})))
    return c


def _iterar_pdfs(zip_bytes: bytes, prefijo: str = "", profundidad: int = 0):
    """Recorre el zip (incluidos zips anidados) devolviendo (nombre, bytes) de cada PDF."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            ruta = PurePosixPath(info.filename)
            if "__MACOSX" in ruta.parts or ruta.name.startswith("."):
                continue
            nombre = prefijo + info.filename
            sufijo = ruta.suffix.lower()
            if sufijo == ".pdf":
                yield nombre, zf.read(info)
            elif sufijo == ".zip" and profundidad < 2:
                yield from _iterar_pdfs(zf.read(info), nombre + "/", profundidad + 1)


def cargar_zip(zip_bytes: bytes) -> ResultadoCarga:
    cuestionarios, errores = [], []
    try:
        pdfs = list(_iterar_pdfs(zip_bytes))
    except zipfile.BadZipFile:
        return ResultadoCarga([], [("(archivo subido)", "no es un .zip válido")])
    if not pdfs:
        errores.append(("(archivo subido)", "el .zip no contiene ningún PDF"))
    for nombre, datos in sorted(pdfs):
        try:
            cuestionarios.append(leer_cuestionario(datos, nombre))
        except Exception as exc:  # se informa en la interfaz, no se detiene el proceso
            errores.append((nombre, str(exc)))
    return ResultadoCarga(cuestionarios, errores)
