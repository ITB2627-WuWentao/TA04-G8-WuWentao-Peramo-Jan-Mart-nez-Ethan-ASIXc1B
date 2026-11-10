#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TA04 - Gestió d'incidències (grup G8)
=====================================
Programa basado en el XML (solo librería estándar, Python 3.8+):

  PASO 1  lee incidencies.xml y FILTRA datos erróneos o inútiles
  PASO 2  muestra la información y estadísticas por pantalla (colores y tabuladores)
  PASO 3  guarda en incidencies.json (si existe, pregunta: sobrescribir / añadir nuevas)

El XML se crea antes con csv_a_xml.py (incidencies.csv -> incidencies.xml).

Uso:
    python3 gestio_incidencies.py
    python3 gestio_incidencies.py --xml otro.xml --json otro.json
    python3 gestio_incidencies.py --sin-color
"""
import argparse
import json
import os
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from statistics import mean
import re
import shutil

# ============================================================================
# CONFIGURACIÓN (edita aquí si cambias algo en el formulario)
# ============================================================================
GRUP = "G8"
DIAS_ATRAS = 365       # una fecha es válida si no es futura ni tiene más de DIAS_ATRAS días
DESC_MIN = 10          # nº mínimo de caracteres de la descripción

CAMPOS = ["id", "data", "reportat_per", "departament", "planta", "equip",
          "tipus", "prioritat", "descripcio", "usuaris_afectats", "causa"]

DEPARTAMENTS = {"Informàtica", "Administració", "Docència", "Direcció"}
PLANTA_RE = re.compile(r"^(Pis|Piso|Planta) [1-4]$")     # "Pis 1", "Piso 1" o "Planta 1"
USUARIS = ["Només 1", "Entre 2 i 5", "Entre 6 i 20", "Més de 20"]

# Todas las variantes aceptadas de "error de usuario" (para no depender del apóstrofo)
VARIANTS_ERROR_USUARI = {"Error de usuari", "Error de l'usuari", "Error de l’usuari",
                         "Error d'usuari", "Error d’usuari", "Error humà"}
EU = "ERROR_USUARI"   # clave interna

# Reglas de coherencia (las mismas que usa el generador de respuestas)
EQUIP_TIPUS = {
    "Ordinador":  {"Maquinari", "Programari", "Xarxa"},
    "Impressora": {"Maquinari", "Programari", "Xarxa"},
    "Projector":  {"Maquinari", "Programari", "Audiovisual"},
    "Switch":     {"Xarxa", "Maquinari"},
    "Càmera":     {"Maquinari", "Xarxa", "Programari", "Audiovisual"},
}
TIPUS_CAUSA = {
    "Maquinari":   {EU, "Desgast o avaria de maquinari", "Problema de xarxa o corrent elèctric", "Desconeguda"},
    "Xarxa":       {EU, "Error de configuració", "Problema de xarxa o corrent elèctric", "Desconeguda"},
    "Programari":  {EU, "Error de configuració", "Actualització o instal·lació de programari",
                    "Virus o atac informàtic", "Desconeguda"},
    "Audiovisual": {EU, "Desgast o avaria de maquinari", "Error de configuració",
                    "Problema de xarxa o corrent elèctric", "Desconeguda"},
}
CAUSES_VALIDES = set().union(*TIPUS_CAUSA.values())

# Nombres "basura" típicos de teclado
NOMBRES_BASURA = ("asdf", "qwer", "xxxx", "aaaa", "test", "prova", "zzzz")
NOMBRE_RE = re.compile(r"^[A-Za-zÀ-ÿ·'’\- ]{3,}$")

def fecha_max():
    """Hoy (fecha actual del sistema, se recalcula cada vez que se ejecuta)."""
    return date.today()


def fecha_min():
    return date.today() - timedelta(days=DIAS_ATRAS)


DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


# ============================================================================
# COLORES (ANSI)
# ============================================================================
class Color:
    activo = True


def _c(txt, codigo):
    return f"\033[{codigo}m{txt}\033[0m" if Color.activo else str(txt)


def negrita(t): return _c(t, "1")
def gris(t):    return _c(t, "90")
def rojo(t):    return _c(t, "91")
def verde(t):   return _c(t, "92")
def amarillo(t): return _c(t, "93")
def azul(t):    return _c(t, "94")
def magenta(t): return _c(t, "95")
def cian(t):    return _c(t, "96")


def color_prioridad(p):
    """Rojo si es crítica (>=8), amarillo si media (5-7), verde si baja."""
    return rojo if p >= 8 else amarillo if p >= 5 else verde


def titulo(texto):
    print()
    print(cian(negrita(f"▌ {texto}")))
    print(gris("\t" + "─" * 60))


def paso(num, texto):
    print()
    print(magenta(negrita(f"══ PASO {num}: {texto} ══")))


def cortar(texto, ancho):
    texto = str(texto)
    return texto if len(texto) <= ancho else texto[:max(1, ancho - 1)] + "…"


def banner(texto):
    linea = "═" * (len(texto) + 4)
    print()
    print(cian(negrita(f"  ╔{linea}╗")))
    print(cian(negrita(f"  ║  {texto}  ║")))
    print(cian(negrita(f"  ╚{linea}╝")))


# ============================================================================
# UTILIDADES
# ============================================================================
def norm(s):
    """Minúsculas y sin acentos, para comparar textos."""
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower().strip()


# ============================================================================
# PASO 1: leer XML y filtrar
# ============================================================================
def leer_xml(ruta):
    raiz = ET.parse(ruta).getroot()
    incidencias = []
    for e in raiz.findall("incidencia"):
        d = {"id": (e.get("id") or "").strip()}
        for campo in CAMPOS[1:]:
            d[campo] = (e.findtext(campo) or "").strip()
        incidencias.append(d)
    return incidencias


def parse_fecha(texto):
    """Acepta AAAA-MM-DD, DD/MM/AAAA y MM/DD/AAAA. Si hay ambigüedad (05/10/2026),
    se prefiere la interpretación que cae dentro del rango válido."""
    if not texto:
        return None
    token = texto.split()[0]
    candidatas = []
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            candidatas.append(datetime.strptime(token, fmt).date())
        except ValueError:
            pass
    for d in candidatas:
        if fecha_min() <= d <= fecha_max():
            return d
    return candidatas[0] if candidatas else None


def clave_causa(causa):
    return EU if causa in VARIANTS_ERROR_USUARI else causa


def validar(inc, ids_validos):
    """Devuelve (incidencia_normalizada | None, [motivos de descarte])."""
    motivos = []

    if not inc["id"]:
        motivos.append("ID vacío")

    fecha = parse_fecha(inc["data"])
    if fecha is None:
        motivos.append("Fecha no válida")
    elif fecha > fecha_max():
        motivos.append("Fecha futura (posterior a hoy)")
    elif fecha < fecha_min():
        motivos.append(f"Fecha demasiado antigua (más de {DIAS_ATRAS} días)")

    rep = inc["reportat_per"]
    if not NOMBRE_RE.match(rep) or any(b in norm(rep) for b in NOMBRES_BASURA):
        motivos.append("Nombre de quien reporta no válido")

    if inc["departament"] not in DEPARTAMENTS:
        motivos.append("Departamento fuera de la lista")
    if not PLANTA_RE.match(inc["planta"]):
        motivos.append("Planta fuera de la lista")

    equip_ok = inc["equip"] in EQUIP_TIPUS
    tipus_ok = inc["tipus"] in TIPUS_CAUSA
    causa_ok = clave_causa(inc["causa"]) in CAUSES_VALIDES
    if not equip_ok:
        motivos.append("Equipo fuera de la lista")
    if not tipus_ok:
        motivos.append("Tipo fuera de la lista")
    if not causa_ok:
        motivos.append("Causa fuera de la lista")

    try:
        prio = int(inc["prioritat"])
        if not 1 <= prio <= 10:
            motivos.append("Prioridad fuera de 1-10")
    except ValueError:
        prio = None
        motivos.append("Prioridad no numérica")

    if len(inc["descripcio"]) < DESC_MIN:
        motivos.append("Descripción vacía o demasiado corta")

    if inc["usuaris_afectats"] not in USUARIS:
        motivos.append("Usuarios afectados fuera de la lista")

    # Coherencia entre campos (solo si cada campo es válido por separado)
    if equip_ok and tipus_ok and inc["tipus"] not in EQUIP_TIPUS[inc["equip"]]:
        motivos.append("Combinación incoherente (equipo/tipo)")
    elif tipus_ok and causa_ok and clave_causa(inc["causa"]) not in TIPUS_CAUSA[inc["tipus"]]:
        motivos.append("Combinación incoherente (tipo/causa)")

    if not motivos and inc["id"] in ids_validos:
        motivos.append("ID duplicado")

    if motivos:
        return None, motivos

    ids_validos.add(inc["id"])
    limpia = dict(inc)
    limpia["data"] = fecha.isoformat()
    limpia["prioritat"] = prio
    return limpia, []


def filtrar(incidencias):
    validas, descartadas = [], []
    ids = set()
    for inc in incidencias:
        ok, motivos = validar(inc, ids)
        if ok:
            validas.append(ok)
        else:
            descartadas.append((inc, motivos))
    return validas, descartadas


# ============================================================================
# PASO 2: mostrar información y estadísticas
# ============================================================================
def barra(n, maximo, ancho=28):
    return "█" * max(1, round(ancho * n / maximo)) if n else ""


def mostrar_conteo(texto, contador, total, color=azul, orden=None, ancho_k=18):
    titulo(texto)
    items = [(k, contador[k]) for k in orden if k in contador] if orden else contador.most_common()
    maximo = max((n for _, n in items), default=1)
    for k, n in items:
        print(f"\t{k:<{ancho_k}}\t{n:>4}\t{100 * n / total:>5.1f}%\t{color(barra(n, maximo))}")


def mostrar_descartadas(todas, descartadas):
    titulo("DATOS DESCARTADOS (erróneos o inútiles)")
    if not descartadas:
        print(verde("\tNo se ha descartado ninguna incidencia."))
        return
    motivos = Counter(m for _, ms in descartadas for m in ms)
    for m, n in motivos.most_common():
        print(f"\t{rojo('✗')} {m:<46}\t{n:>4}")
    print()
    print(gris("\tEjemplos:"))
    for inc, ms in descartadas[:12]:
        print(f"\t{rojo(inc['id'] or '(sin id)'):<22}\t{'; '.join(ms)}")
    if len(descartadas) > 12:
        print(gris(f"\t… y {len(descartadas) - 12} más"))


def mostrar_tabla(validas, n=10):
    """Tabla alineada con las primeras incidencias válidas (prioridad en color)."""
    titulo(f"PRIMERAS {min(n, len(validas))} INCIDENCIAS VÁLIDAS")
    if not validas:
        return
    ancho_term = shutil.get_terminal_size((110, 20)).columns
    w = [8, 10, 17, 10, 11, 3]
    resto = ancho_term - sum(w) - 2 * len(w) - 10
    wd = max(20, min(resto, 60))
    cab = ["ID", "Fecha", "Reporta", "Equipo", "Tipo", "Pri"]
    print("\t" + negrita("  ".join(f"{c:<{x}}" for c, x in zip(cab, w)) + "  Descripción"))
    print(gris("\t" + "─" * min(ancho_term - 10, sum(w) + 2 * len(w) + wd)))
    for i in validas[:n]:
        col = color_prioridad(i["prioritat"])
        fila = [cortar(i["id"], w[0]), i["data"], cortar(i["reportat_per"], w[2]),
                cortar(i["equip"], w[3]), cortar(i["tipus"], w[4])]
        print("\t" + "  ".join(f"{c:<{x}}" for c, x in zip(fila, w)) + "  "
              + col(f"{i['prioritat']:>3}") + "  " + cortar(i["descripcio"], wd))
    if len(validas) > n:
        print(gris(f"\t… y {len(validas) - n} más (todas se guardan en el JSON)"))


def mostrar_estadisticas(validas, todas_n):
    total = len(validas)
    if total == 0:
        print(rojo("\nNo hay incidencias válidas para analizar."))
        return

    # ---- Resumen general
    titulo("RESUMEN GENERAL")
    prios = [i["prioritat"] for i in validas]
    criticas = [i for i in validas if i["prioritat"] >= 8]
    print(f"\tIncidencias leídas del XML\t\t{negrita(todas_n)}")
    print(f"\tIncidencias válidas\t\t\t{verde(negrita(total))}\t({100 * total / todas_n:.1f}%)")
    print(f"\tIncidencias descartadas\t\t\t{rojo(negrita(todas_n - total))}")
    print(f"\tPrioridad media\t\t\t\t{negrita(f'{mean(prios):.2f}')} / 10")
    print(f"\tIncidencias críticas (prioridad ≥ 8)\t{rojo(negrita(len(criticas)))}"
          f"\t({100 * len(criticas) / total:.1f}%)")
    grandes = sum(1 for i in validas if i["usuaris_afectats"] in ("Entre 6 i 20", "Més de 20"))
    print(f"\tAfectan a más de 5 usuarios\t\t{amarillo(negrita(grandes))}\t({100 * grandes / total:.1f}%)")

    # ---- Distribuciones
    mostrar_conteo("POR DEPARTAMENTO", Counter(i["departament"] for i in validas), total, azul)
    mostrar_conteo("POR EQUIPO", Counter(i["equip"] for i in validas), total, magenta)
    mostrar_conteo("POR TIPO DE INCIDENCIA", Counter(i["tipus"] for i in validas), total, cian)
    mostrar_conteo("POR PLANTA", Counter(i["planta"] for i in validas), total, azul)
    mostrar_conteo("CAUSA PROBABLE", Counter(i["causa"] for i in validas), total, amarillo, ancho_k=44)
    mostrar_conteo("USUARIOS AFECTADOS", Counter(i["usuaris_afectats"] for i in validas), total,
                   rojo, orden=USUARIS)

    # ---- Prioridad por departamento y críticas por equipo
    titulo("PRIORIDAD MEDIA POR DEPARTAMENTO")
    por_dep = defaultdict(list)
    for i in validas:
        por_dep[i["departament"]].append(i["prioritat"])
    for dep, ps in sorted(por_dep.items(), key=lambda x: -mean(x[1])):
        m = mean(ps)
        print(f"\t{dep:<18}\t{color_prioridad(round(m))(f'{m:.2f}')}\t{color_prioridad(round(m))(barra(m, 10))}")

    titulo("EQUIPOS CON MÁS INCIDENCIAS CRÍTICAS (≥ 8)")
    crit_eq = Counter(i["equip"] for i in criticas)
    if crit_eq:
        mx = max(crit_eq.values())
        for eq, n in crit_eq.most_common():
            print(f"\t{eq:<18}\t{n:>4}\t{rojo(barra(n, mx))}")
    else:
        print(verde("\tNo hay incidencias críticas."))

    # ---- Evolución temporal
    titulo("EVOLUCIÓN EN EL TIEMPO")
    por_dia = Counter(i["data"] for i in validas)
    dia, n = por_dia.most_common(1)[0]
    d = date.fromisoformat(dia)
    print(f"\tDía con más incidencias\t{negrita(dia)} ({DIAS[d.weekday()]})\t{amarillo(n)}")
    por_semana = Counter(date.fromisoformat(i["data"]).isocalendar()[1] for i in validas)
    mx = max(por_semana.values())
    for sem in sorted(por_semana):
        print(f"\tSemana {sem:<12}\t{por_semana[sem]:>4}\t{verde(barra(por_semana[sem], mx))}")

    # ---- Top 5 más críticas
    titulo("TOP 5 INCIDENCIAS MÁS CRÍTICAS")
    top = sorted(validas, key=lambda i: (-i["prioritat"], i["data"]))[:5]
    for i in top:
        col = color_prioridad(i["prioritat"])
        print(f"\t{col(str(i['prioritat']).rjust(2))}\t{i['id']}\t{i['data']}\t{i['equip']:<11}\t"
              f"{i['departament']:<14}\t{i['descripcio'][:55]}")


# ============================================================================
# PASO 3: guardar en JSON
# ============================================================================
def cargar_json(ruta):
    """Devuelve la lista de incidencias del JSON, o None si el fichero no es válido."""
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(datos, dict):
        datos = datos.get("incidencies")
    return datos if isinstance(datos, list) else None


def escribir_json(ruta, lista):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({"total": len(lista), "incidencies": lista}, f, ensure_ascii=False, indent=2)


def guardar_json(validas, ruta):
    if not os.path.exists(ruta):
        escribir_json(ruta, validas)
        print(verde(f"\t✔ {ruta} no existía: creado con {len(validas)} incidencias."))
        return

    existentes = cargar_json(ruta)
    print(amarillo(f"\t⚠ El fichero {ruta} ya existe"
                   + (f" ({len(existentes)} incidencias)." if existentes is not None
                      else " pero no es un JSON válido (solo se puede sobrescribir).")))
    print("\t  [a] Sobrescribirlo (borra lo anterior y escribe todas las incidencias de nuevo)")
    print("\t  [b] Añadir solo las incidencias nuevas (sin repetir IDs)")
    while True:
        try:
            r = input(cian("\t¿Qué quieres hacer? (a/b): ")).strip().lower()
        except EOFError:
            print(rojo("\n\tNo se ha podido leer la respuesta: no se guarda nada."))
            return
        if r == "a":
            escribir_json(ruta, validas)
            print(verde(f"\t✔ Sobrescrito: {len(validas)} incidencias."))
            return
        if r == "b":
            if existentes is None:
                print(rojo("\tEl JSON existente no es válido; elige la opción a."))
                continue
            ids = {i.get("id") for i in existentes}
            nuevas = [i for i in validas if i["id"] not in ids]
            escribir_json(ruta, existentes + nuevas)
            print(verde(f"\t✔ Añadidas {len(nuevas)} incidencias nuevas"
                        f" ({len(validas) - len(nuevas)} ya existían). Total: {len(existentes) + len(nuevas)}."))
            return
        print(rojo("\tOpción no válida: escribe a o b."))


# ============================================================================
# PROGRAMA PRINCIPAL
# ============================================================================
def main():
    ap = argparse.ArgumentParser(description="TA04 - XML -> filtro -> estadísticas -> JSON")
    ap.add_argument("--xml", default="incidencies.xml")
    ap.add_argument("--json", default="incidencies.json")
    ap.add_argument("--sin-color", action="store_true", help="desactiva los colores ANSI")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    if os.name == "nt":
        os.system("")                                      # activa ANSI en la consola de Windows
    Color.activo = bool(os.environ.get("FORCE_COLOR")) or (
        sys.stdout.isatty() and not args.sin_color and not os.environ.get("NO_COLOR"))

    banner(f"TA04 · Gestió d'incidències · {GRUP}")
    print(gris(f"\tFecha actual: {fecha_max().isoformat()} "
               f"(se aceptan fechas desde {fecha_min().isoformat()} hasta hoy)"))

    # ---- PASO 1
    paso(1, "Leer el XML y filtrar datos erróneos")
    if not os.path.exists(args.xml):
        sys.exit(rojo(f"\tNo encuentro el fichero {args.xml}. Créalo antes con csv_a_xml.py."))
    try:
        todas = leer_xml(args.xml)
    except ET.ParseError as e:
        linea = e.position[0] if getattr(e, "position", None) else "?"
        sys.exit(rojo(f"\tEl fichero {args.xml} no es un XML válido (error cerca de la línea {linea})."))
    except UnicodeDecodeError:
        sys.exit(rojo(f"\tNo puedo leer {args.xml}: caracteres no válidos."))
    except OSError:
        sys.exit(rojo(f"\tNo puedo leer {args.xml}."))
    if not todas:
        sys.exit(rojo(f"\t{args.xml} no contiene ninguna incidencia."))
    validas, descartadas = filtrar(todas)
    print(f"\t{len(todas)} incidencias leídas → {verde(str(len(validas)))} válidas, "
          f"{rojo(str(len(descartadas)))} descartadas.")
    ancho_b = 40
    k = round(ancho_b * len(validas) / len(todas))
    print("\t" + verde("█" * k) + rojo("█" * (ancho_b - k))
          + gris(f"  {100 * len(validas) / len(todas):.1f}% válidas"))
    mostrar_descartadas(todas, descartadas)

    # ---- PASO 2
    paso(2, "Información y estadísticas")
    mostrar_tabla(validas)
    mostrar_estadisticas(validas, len(todas))

    # ---- PASO 3
    paso(3, "Guardar en JSON")
    try:
        guardar_json(validas, args.json)
    except OSError:
        sys.exit(rojo(f"\tNo puedo escribir {args.json}."))
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\n\tCancelado por el usuario.")