"""
Genera un .zip de cuestionarios de prueba a partir de un cuestionario real
(rellenando su formulario con respuestas variadas).

Uso:
    python herramientas/generar_cuestionarios_prueba.py cuestionario_ejemplo.pdf salida.zip [n]
"""
import io
import random
import sys
import zipfile

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject

ETIQUETAS = {1: "/Completamente en desacuerdo", 2: "/En desacuerdo", 3: "/De acuerdo", 4: "/Completamente de acuerdo"}

# Tendencia de cada campo (probabilidades de 1, 2, 3, 4)
PERFIL = {
    "ID_BUENA_ORGANIZACION": (0.05, 0.15, 0.5, 0.3),
    "ID_NUM_ALUMNOS_ADECUADO": (0, 0.1, 0.4, 0.5),
    "ID_CONTENIDOS_SEGUN_NECESIDADES": (0, 0.1, 0.5, 0.4),
    "ID_CONTENIDOS_SEGUN_TEORIA_PRACTICA": (0, 0.15, 0.45, 0.4),
    "ID_DURACION_SUFICIENTE": (0.25, 0.4, 0.25, 0.1),
    "ID_HORARIO_FAVORABLE": (0, 0.1, 0.4, 0.5),
    "ID_FORMADOR_FACILITADOR": (0, 0, 0.2, 0.8),
    "ID_FORMADOR_CONOCE_TEMA": (0, 0, 0.1, 0.9),
    "ID_TUTOR_FACILITADOR": (0, 0, 0.3, 0.7),
    "ID_TUTOR_CONOCE_TEMA": (0, 0, 0.2, 0.8),
    "ID_MEDIOS_COMPRENSIBLES": (0, 0.1, 0.6, 0.3),
    "ID_MEDIOS_ACTUALIZADOS": (0, 0.2, 0.5, 0.3),
    "ID_INSTALACIONES_ADECUADAS": (0.1, 0.4, 0.4, 0.1),
    "ID_MEDIOS_TECNICOS_ADECUADOS": (0.15, 0.35, 0.4, 0.1),
    "ID_TELEFORMACION_GUIA": (0, 0.1, 0.6, 0.3),
    "ID_TELEFORMACION_MEDIOS": (0, 0.1, 0.6, 0.3),
    "ID_INCORPORACION_MERCADO": (0.05, 0.15, 0.5, 0.3),
    "Habilidades_trabajar_en_formado": (0, 0.05, 0.4, 0.55),
    "ID_CONOCIMIENTOS_PUESTO_TRABAJO": (0.05, 0.2, 0.5, 0.25),
    "ID_PROGRESAR_CARRERA": (0, 0.1, 0.5, 0.4),
    "ID_DESARROLLO_PERSONAL": (0, 0.05, 0.45, 0.5),
    "ID_GRADO_SATISFACCION": (0, 0.1, 0.45, 0.45),
}

COMENTARIOS = [
    "- Profesor excelente, ha puesto muchos ejemplos y ha resuelto todas las dudas con claridad\r- No ha dado tiempo a dar una parte del temario, el contenido era extenso y creo que ha faltado tiempo",
    "El formador domina la materia y lo explica de forma muy amena. El aula era pequeña y hacía mucho calor.",
    "Muy útil para aplicar en mi día a día como Scrum Master, aunque echo en falta más casos prácticos.",
    "Curso muy completo. Sería conveniente ampliar la duración, se queda corto para todo el temario.",
    "",
    "El proyector falló varias veces y la conexión wifi era muy lenta.",
    "Me ha gustado mucho la dinámica de las sesiones y los ejercicios en grupo. Lo recomiendo.",
    "La documentación entregada es clara y está actualizada.",
    "Nada que añadir",
    "Demasiado contenido para tan pocas horas, íbamos con prisa al final.",
    "El profesor muy cercano y con mucha experiencia real en proyectos ágiles.",
    "Las sillas eran incómodas para tantas horas. Por lo demás, todo bien.",
    "",
    "Buena organización y la información previa llegó a tiempo.",
    "Habría que dedicar más tiempo a la parte práctica y menos a la teoría.",
]


def rellenar(base: bytes, valores: dict, texto: dict) -> bytes:
    lector = PdfReader(io.BytesIO(base))
    escritor = PdfWriter()
    escritor.append(lector)
    for pagina in escritor.pages:
        for anot in pagina.get("/Annots", []) or []:
            anot = anot.get_object()
            padre = anot.get("/Parent")
            nombre = anot.get("/T") or (padre.get_object().get("/T") if padre else None)
            if nombre in valores:
                campo = padre.get_object() if padre else anot
                v = valores[nombre]
                campo[NameObject("/V")] = NameObject(v)
                estados = list(anot.get("/AP", {}).get("/N", {}).keys())
                anot[NameObject("/AS")] = NameObject(v if v in estados else "/Off")
            if nombre in texto:
                campo = padre.get_object() if padre else anot
                campo[NameObject("/V")] = TextStringObject(texto[nombre])
    escritor.set_need_appearances_writer(True)
    salida = io.BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def main():
    origen, destino = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    random.seed(7)
    base = open(origen, "rb").read()
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(n):
            valores = {campo: ETIQUETAS[random.choices([1, 2, 3, 4], p)[0]] for campo, p in PERFIL.items()}
            if random.random() < 0.08:
                valores["ID_INCORPORACION_MERCADO"] = "/No contesta"
            valores["ID_PRUEBAS_EVALUACION"] = random.choice(["/Si", "/Si", "/No"])
            valores["ID_ACREDITACION"] = random.choice(["/Si", "/No", "/No"])
            valores["ID_RECOMENDARIA_CURSO"] = "/Si" if random.random() < 0.85 else "/No"
            texto = {"D_OBSERVACION": COMENTARIOS[i % len(COMENTARIOS)]}
            zf.writestr(f"Cuestionarios/Cuestionario_{i + 1:03d}.pdf", rellenar(base, valores, texto))
    print(f"{n} cuestionarios -> {destino}")


if __name__ == "__main__":
    main()
