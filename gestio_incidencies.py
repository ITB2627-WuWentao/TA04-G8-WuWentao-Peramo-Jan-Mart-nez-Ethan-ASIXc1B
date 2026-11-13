#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TA04 - Gestió d'incidències (grup G8)
=====================================
Un solo programa, sin instalar nada (solo Python 3.8+ y, si quieres, un navegador).
Funciona igual en Windows, macOS y Linux.

  PASO 1  lee incidencies.xml y FILTRA los datos erróneos o inútiles
  PASO 2  muestra la información y estadísticas en la TERMINAL (colores, tabuladores, barras)
  PASO 3  genera informe_incidencies.html: el mismo informe en versión gráfica
  PASO 4  guarda incidencies.json (si existe, pregunta: a = sobrescribir / b = añadir nuevas)
  PASO 5  abre el informe en el navegador

El XML se crea antes con csv_a_xml.py (incidencies.csv -> incidencies.xml).

Uso:
    python3 gestio_incidencies.py
    python3 gestio_incidencies.py --no-abrir        (no abre el navegador)
    python3 gestio_incidencies.py --sin-web         (solo terminal, sin informe HTML)
    python3 gestio_incidencies.py --sin-color       (terminal sin colores)
    python3 gestio_incidencies.py --xml otro.xml --json otro.json --html otro.html
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
import webbrowser
from pathlib import Path

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
    if not isinstance(datos, list) or not all(isinstance(i, dict) for i in datos):
        return None                       # no es una lista de incidencias: JSON no válido
    return datos


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
# INFORME WEB
# ============================================================================
ROJO, AMBAR, VERDE = "#dc2626", "#d97706", "#16a34a"
AZUL, MORADO, CIAN = "#2563eb", "#7c3aed", "#0891b2"


def color_prio_hex(p):
    return ROJO if p >= 8 else AMBAR if p >= 5 else VERDE


# ----------------------------------------------------------------------------
# Datos para el informe
# ----------------------------------------------------------------------------
COLS = [("id", "ID"), ("data", "Fecha"), ("reportat_per", "Reporta"), ("departament", "Departamento"),
        ("planta", "Planta"), ("equip", "Equipo"), ("tipus", "Tipo"), ("prioritat", "Pri."),
        ("usuaris_afectats", "Usuarios"), ("causa", "Causa"), ("descripcio", "Descripción")]


def preparar_datos(todas, validas, descartadas, nombre_xml):
    n, v = len(todas), len(validas)
    crit = [i for i in validas if i["prioritat"] >= 8]
    grandes = sum(1 for i in validas if i["usuaris_afectats"] in ("Entre 6 i 20", "Més de 20"))
    pct = lambda a, b: f" ({100 * a / b:.1f}%)" if b else ""
    kpi = [
        {"label": "Incidencias leídas del XML", "value": str(n), "color": AZUL},
        {"label": "Incidencias válidas", "value": f"{v}{pct(v, n)}", "color": VERDE},
        {"label": "Incidencias descartadas", "value": str(n - v), "color": ROJO},
        {"label": "Prioridad media (de 10)", "value": f"{mean(i['prioritat'] for i in validas):.2f}" if v else "–",
         "color": AMBAR},
        {"label": "Críticas (prioridad ≥ 8)", "value": f"{len(crit)}{pct(len(crit), v)}", "color": ROJO},
        {"label": "Afectan a más de 5 usuarios", "value": f"{grandes}{pct(grandes, v)}", "color": MORADO},
    ]

    dia_txt = ""
    if validas:
        dia, k = Counter(i["data"] for i in validas).most_common(1)[0]
        dia_txt = f"Día con más incidencias: {dia} ({DIAS[date.fromisoformat(dia).weekday()]}) · {k} incidencias"

    top = sorted(validas, key=lambda i: (-i["prioritat"], i["data"]))[:5]

    charts = []
    if validas:
        cnt = lambda campo: [[k, c, None] for k, c in Counter(i[campo] for i in validas).most_common()]
        por_dep = defaultdict(list)
        for i in validas:
            por_dep[i["departament"]].append(i["prioritat"])
        usu = Counter(i["usuaris_afectats"] for i in validas)
        prios = Counter(i["prioritat"] for i in validas)
        semanas = Counter(date.fromisoformat(i["data"]).isocalendar()[1] for i in validas)
        crit_eq = Counter(i["equip"] for i in crit).most_common()
        charts = [
            {"title": "Incidencias por departamento", "items": cnt("departament"), "color": AZUL},
            {"title": "Incidencias por equipo", "items": cnt("equip"), "color": MORADO},
            {"title": "Por tipo de incidencia", "items": cnt("tipus"), "color": CIAN},
            {"title": "Por planta", "items": cnt("planta"), "color": AZUL},
            {"title": "Causa probable", "items": cnt("causa"), "color": AMBAR},
            {"title": "Usuarios afectados", "items": [[k, usu[k], None] for k in USUARIS if k in usu],
             "color": ROJO},
            {"title": "Prioridad media por departamento", "dec": 2, "color": AZUL,
             "items": [[d, round(mean(p), 2), color_prio_hex(round(mean(p)))]
                       for d, p in sorted(por_dep.items(), key=lambda x: -mean(x[1]))]},
            {"title": "Equipos con más incidencias críticas (≥ 8)", "items": [[k, c, None] for k, c in crit_eq],
             "color": ROJO},
            {"title": "Distribución de la prioridad (1-10)", "color": AZUL,
             "items": [[str(p), prios[p], color_prio_hex(p)] for p in range(1, 11)]},
            {"title": "Incidencias por semana del año", "color": VERDE,
             "items": [[f"Semana {s}", semanas[s], None] for s in sorted(semanas)]},
        ]

    motivos = Counter(m for _, ms in descartadas for m in ms).most_common()
    return {
        "titulo": f"TA04 · Gestió d'incidències · {GRUP}",
        "fecha": f"Fecha actual: {fecha_max().isoformat()} · se aceptan fechas desde "
                 f"{fecha_min().isoformat()} hasta hoy",
        "fuente": f"{nombre_xml} · generado el {datetime.now().strftime('%d/%m/%Y a las %H:%M:%S')}",
        "n": n, "nv": v, "kpi": kpi, "dia": dia_txt,
        "top": [{k: i[k] for k in ("id", "data", "equip", "departament", "prioritat", "descripcio")} for i in top],
        "cols": [{"k": k, "t": t} for k, t in COLS],
        "validas": [[i[k] for k, _ in COLS] for i in validas],
        "dcols": [{"k": "id", "t": "ID"}, {"k": "m", "t": "Motivo(s)"}, {"k": "data", "t": "Fecha"},
                  {"k": "rep", "t": "Reporta"}, {"k": "desc", "t": "Descripción"}],
        "descartadas": [[inc["id"] or "(sin id)", "; ".join(ms), inc["data"], inc["reportat_per"],
                         inc["descripcio"]] for inc, ms in descartadas],
        "motivos": motivos,
        "charts": charts,
        "deps": sorted({i["departament"] for i in validas}),
    }


# ----------------------------------------------------------------------------
# Plantilla HTML (CSS y JS dentro: un solo fichero, sin internet)
# ----------------------------------------------------------------------------
PLANTILLA = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TA04 · Gestió d'incidències · G8</title>
<style>
:root{--bg:#f3f5f9;--card:#fff;--line:#dfe3ea;--text:#1f2937;--muted:#6b7280;--blue:#2563eb;
--red:#dc2626;--amber:#d97706;--green:#16a34a;--head:#eef1f6;--sel:#dbeafe}
@media (prefers-color-scheme:dark){:root{--bg:#0f172a;--card:#1e293b;--line:#334155;--text:#e5e7eb;
--muted:#94a3b8;--head:#273449;--sel:#1e3a5f;--blue:#60a5fa;--red:#f87171;--amber:#fbbf24;--green:#4ade80}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,Ubuntu,sans-serif}
header{padding:22px 28px 0}
h1{margin:0;font-size:26px}
.sub{color:var(--muted);margin-top:2px}
nav{display:flex;gap:6px;padding:16px 28px 0;flex-wrap:wrap;border-bottom:1px solid var(--line)}
nav button{border:1px solid var(--line);border-bottom:none;background:var(--head);color:var(--muted);
padding:10px 20px;border-radius:10px 10px 0 0;cursor:pointer;font:inherit}
nav button.on{background:var(--card);color:var(--blue);font-weight:600}
main{padding:20px 28px 40px;max-width:1400px;margin:0 auto}
section{display:none}section.on{display:block}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px}
.card .v{font-size:30px;font-weight:700}.card .l{color:var(--muted)}
.bar{display:flex;height:30px;border-radius:8px;overflow:hidden;margin:18px 0 10px;font-weight:600;color:#fff;font-size:13px}
.bar div{display:flex;align-items:center;padding:0 12px;white-space:nowrap}
h2{font-size:17px;margin:24px 0 10px}
.tw{overflow:auto;border:1px solid var(--line);border-radius:12px;background:var(--card)}
table{border-collapse:collapse;width:100%}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{background:var(--head);position:sticky;top:0;cursor:pointer;user-select:none;font-size:13px}
td.d{white-space:normal;min-width:260px}
tr:hover td{background:var(--sel)}
.c{text-align:center}
.tools{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:6px 0 12px}
input,select{font:inherit;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--text)}
button.p{font:inherit;padding:6px 14px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--text);cursor:pointer}
button.p:disabled{opacity:.4;cursor:default}
.muted{color:var(--muted)}
.pag{display:flex;gap:10px;align-items:center;margin-top:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px}
.ch h3{margin:0 0 10px;font-size:15px}
.row{display:grid;grid-template-columns:minmax(110px,230px) 1fr 54px;gap:10px;align-items:center;margin:5px 0;font-size:14px}
.row .t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .k{height:16px;background:var(--head);border-radius:4px}
.row .k i{display:block;height:100%;border-radius:4px}
.row .n{color:var(--muted);text-align:right}
@media (max-width:520px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<header><h1 id="titulo"></h1><div class="sub" id="fecha"></div></header>
<nav id="nav"></nav>
<main>
<section id="s-resumen"></section>
<section id="s-validas"></section>
<section id="s-desc"></section>
<section id="s-stats"></section>
<p class="muted" id="pie"></p>
</main>
<script type="application/json" id="data">__DATOS__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const el = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c; if (x !== undefined) e.textContent = x; return e; };
const pcol = p => p >= 8 ? 'var(--red)' : p >= 5 ? 'var(--amber)' : 'var(--green)';

document.getElementById('titulo').textContent = D.titulo;
document.getElementById('fecha').textContent = D.fecha;
document.getElementById('pie').textContent = D.fuente;

// ---- pestañas
const tabs = [['s-resumen','Resumen'],['s-validas','Incidencias válidas'],['s-desc','Descartadas'],['s-stats','Estadísticas']];
const nav = document.getElementById('nav');
tabs.forEach(([id, t], i) => {
  const b = el('button', i ? '' : 'on', t); b.onclick = () => {
    nav.querySelectorAll('button').forEach(x => x.className = ''); b.className = 'on';
    document.querySelectorAll('section').forEach(s => s.className = s.id === id ? 'on' : '');
  }; nav.appendChild(b);
});
document.getElementById('s-resumen').className = 'on';

// ---- resumen
(function () {
  const s = document.getElementById('s-resumen');
  const cards = el('div', 'cards');
  D.kpi.forEach(k => { const c = el('div', 'card'); const v = el('div', 'v', k.value); v.style.color = k.color;
    c.append(v, el('div', 'l', k.label)); cards.appendChild(c); });
  s.appendChild(cards);
  if (D.n) {
    const bar = el('div', 'bar'); const a = el('div', '', D.nv + ' válidas'); a.style.background = 'var(--green)';
    a.style.width = (100 * D.nv / D.n) + '%'; bar.appendChild(a);
    if (D.n - D.nv) { const r = el('div', '', D.n - D.nv); r.style.background = 'var(--red)'; r.style.flex = '1'; bar.appendChild(r); }
    s.appendChild(bar);
  }
  s.appendChild(el('div', '', D.dia));
  s.appendChild(el('h2', '', 'Top 5 incidencias más críticas'));
  const w = el('div', 'tw'), t = el('table'); const hr = el('tr');
  ['ID','Fecha','Equipo','Departamento','Pri.','Descripción'].forEach(x => hr.appendChild(el('th', '', x)));
  t.appendChild(hr);
  D.top.forEach(i => { const r = el('tr');
    [i.id, i.data, i.equip, i.departament, i.prioritat].forEach((x, n) => { const td = el('td', n === 4 ? 'c' : '', x);
      td.style.color = pcol(i.prioritat); r.appendChild(td); });
    const d = el('td', 'd', i.descripcio); d.style.color = pcol(i.prioritat); r.appendChild(d); t.appendChild(r); });
  w.appendChild(t); s.appendChild(w);
})();

// ---- tabla genérica con búsqueda, orden y paginación
function tabla(root, cols, rows, opt) {
  const PS = 100; let q = '', dep = 'Todos', crit = false, sk = -1, inv = false, pg = 0;
  const tools = el('div', 'tools'); const inp = el('input'); inp.type = 'search'; inp.placeholder = 'Buscar…';
  tools.append(el('span', 'muted', 'Buscar:'), inp);
  let sel, chk;
  if (opt.filtros) {
    sel = el('select'); ['Todos'].concat(D.deps).forEach(d => { const o = el('option', '', d); o.value = d; sel.appendChild(o); });
    const lc = el('label'); chk = el('input'); chk.type = 'checkbox'; lc.append(chk, document.createTextNode(' Solo críticas (≥ 8)'));
    tools.append(el('span', 'muted', 'Departamento:'), sel, lc);
  }
  const cnt = el('span', 'muted'); tools.appendChild(cnt); root.appendChild(tools);
  const w = el('div', 'tw'); w.style.maxHeight = '70vh'; const t = el('table'); const th = el('thead'), tb = el('tbody');
  const hr = el('tr'); cols.forEach((c, i) => { const h = el('th', '', c.t); h.onclick = () => { inv = (sk === i) ? !inv : false; sk = i; pg = 0; draw(); }; hr.appendChild(h); });
  th.appendChild(hr); t.append(th, tb); w.appendChild(t); root.appendChild(w);
  const pag = el('div', 'pag'); const bp = el('button', 'p', '← Anterior'), bn = el('button', 'p', 'Siguiente →'), info = el('span', 'muted');
  pag.append(bp, bn, info); root.appendChild(pag);
  bp.onclick = () => { pg--; draw(); }; bn.onclick = () => { pg++; draw(); };
  inp.oninput = () => { q = inp.value.trim().toLowerCase(); pg = 0; draw(); };
  if (sel) { sel.onchange = () => { dep = sel.value; pg = 0; draw(); }; chk.onchange = () => { crit = chk.checked; pg = 0; draw(); }; }
  const iDep = cols.findIndex(c => c.k === 'departament'), iPri = cols.findIndex(c => c.k === 'prioritat');
  function draw() {
    let f = rows.filter(r => (dep === 'Todos' || r[iDep] === dep) && (!crit || r[iPri] >= 8) &&
      (!q || r.join(' ').toLowerCase().includes(q)));
    if (sk >= 0) f = f.slice().sort((a, b) => { const x = a[sk], y = b[sk];
      const c = (typeof x === 'number' && typeof y === 'number') ? x - y : String(x).localeCompare(String(y), 'es');
      return inv ? -c : c; });
    const np = Math.max(1, Math.ceil(f.length / PS)); pg = Math.min(Math.max(pg, 0), np - 1);
    hr.querySelectorAll('th').forEach((h, i) => h.textContent = cols[i].t + (i === sk ? (inv ? ' ▼' : ' ▲') : ''));
    tb.textContent = '';
    f.slice(pg * PS, pg * PS + PS).forEach(r => { const tr = el('tr');
      r.forEach((x, i) => { const td = el('td', cols[i].k === 'descripcio' || cols[i].k === 'desc' || cols[i].k === 'm' ? 'd' : (i === iPri ? 'c' : ''), x);
        if (iPri >= 0) td.style.color = pcol(r[iPri]); tr.appendChild(td); });
      tb.appendChild(tr); });
    cnt.textContent = 'Mostrando ' + f.length + ' de ' + rows.length;
    info.textContent = 'Página ' + (pg + 1) + ' de ' + np; bp.disabled = pg === 0; bn.disabled = pg >= np - 1;
  }
  draw();
}
tabla(document.getElementById('s-validas'), D.cols, D.validas, {filtros: true});

// ---- descartadas
(function () {
  const s = document.getElementById('s-desc');
  s.appendChild(el('h2', '', 'Motivos de descarte'));
  const w = el('div', 'tw'), t = el('table'); const hr = el('tr');
  ['Motivo', 'Incidencias'].forEach(x => hr.appendChild(el('th', '', x))); t.appendChild(hr);
  if (!D.motivos.length) { const r = el('tr'); r.appendChild(el('td', '', 'No se ha descartado ninguna incidencia.')); t.appendChild(r); }
  D.motivos.forEach(([m, n]) => { const r = el('tr'); r.append(el('td', '', m), el('td', '', n)); t.appendChild(r); });
  w.appendChild(t); s.appendChild(w); s.appendChild(el('h2', '', 'Incidencias descartadas'));
  tabla(s, D.dcols, D.descartadas, {});
})();

// ---- estadísticas
(function () {
  const s = document.getElementById('s-stats');
  if (!D.charts.length) { s.appendChild(el('p', 'muted', 'No hay incidencias válidas para analizar.')); return; }
  const g = el('div', 'grid');
  D.charts.forEach(c => { const card = el('div', 'card ch'); card.appendChild(el('h3', '', c.title));
    const mx = Math.max(...c.items.map(i => i[1]), 0) || 1;
    c.items.forEach(([lab, val, col]) => { const r = el('div', 'row'); const t = el('div', 't', lab); t.title = lab;
      const k = el('div', 'k'), b = el('i'); b.style.width = Math.max(1.5, 100 * val / mx) + '%'; b.style.background = col || c.color; k.appendChild(b);
      r.append(t, k, el('div', 'n', c.dec ? val.toFixed(c.dec) : val)); card.appendChild(r); });
    g.appendChild(card); });
  s.appendChild(g);
})();
</script>
</body>
</html>
"""


def generar_html(datos, ruta):
    js = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    Path(ruta).write_text(PLANTILLA.replace("__DATOS__", js), encoding="utf-8")


# ----------------------------------------------------------------------------
# Programa principal
# ----------------------------------------------------------------------------
def abrir_navegador(ruta):
    """Abre el informe. En Linux sin escritorio no lo intenta (evita navegadores de texto)."""
    if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    try:
        return webbrowser.open(Path(ruta).resolve().as_uri())
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description="TA04 - Gestió d'incidències: XML -> filtro -> estadísticas -> HTML -> JSON")
    ap.add_argument("--xml", default="incidencies.xml")
    ap.add_argument("--json", default="incidencies.json")
    ap.add_argument("--html", default="informe_incidencies.html")
    ap.add_argument("--no-abrir", action="store_true", help="no abre el navegador")
    ap.add_argument("--sin-web", action="store_true", help="no genera el informe HTML")
    ap.add_argument("--sin-color", action="store_true", help="desactiva los colores ANSI")
    args = ap.parse_args()

    # Rutas pasadas a mano: relativas a donde se ejecuta. Rutas por defecto: carpeta del programa
    # (así funciona aunque lo ejecuten desde otra carpeta).
    for k in ("xml", "json", "html"):
        if getattr(args, k) != ap.get_default(k):
            setattr(args, k, os.path.abspath(getattr(args, k)))
    try:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
    except OSError:
        pass

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
    xml_n = os.path.basename(args.xml)

    # ---- PASO 1
    paso(1, "Leer el XML y filtrar datos erróneos")
    if not os.path.isfile(args.xml):
        sys.exit(rojo(f"\tNo encuentro el fichero {xml_n}. Créalo antes con csv_a_xml.py."))
    try:
        todas = leer_xml(args.xml)
    except ET.ParseError as e:
        linea = e.position[0] if getattr(e, "position", None) else "?"
        sys.exit(rojo(f"\tEl fichero {xml_n} no es un XML válido (error cerca de la línea {linea})."))
    except UnicodeDecodeError:
        sys.exit(rojo(f"\tNo puedo leer {xml_n}: caracteres no válidos."))
    except OSError:
        sys.exit(rojo(f"\tNo puedo leer {xml_n}."))
    if not todas:
        sys.exit(rojo(f"\t{xml_n} no contiene ninguna incidencia."))
    validas, descartadas = filtrar(todas)
    print(f"\t{len(todas)} incidencias leídas → {verde(str(len(validas)))} válidas, "
          f"{rojo(str(len(descartadas)))} descartadas.")
    k = round(40 * len(validas) / len(todas))
    print("\t" + verde("█" * k) + rojo("█" * (40 - k))
          + gris(f"  {100 * len(validas) / len(todas):.1f}% válidas"))
    mostrar_descartadas(todas, descartadas)

    # ---- PASO 2
    paso(2, "Información y estadísticas")
    mostrar_tabla(validas)
    mostrar_estadisticas(validas, len(todas))

    # ---- PASO 3
    html_ok = False
    if not args.sin_web:
        paso(3, "Generar el informe gráfico (HTML)")
        try:
            generar_html(preparar_datos(todas, validas, descartadas, xml_n), args.html)
            html_ok = True
            print(verde(f"\t✔ Informe creado: {os.path.basename(args.html)}"))
        except OSError:
            print(rojo(f"\tNo puedo escribir {os.path.basename(args.html)}: se sigue sin informe web."))

    # ---- PASO 4
    paso(4, "Guardar en JSON")
    if not validas:
        print(amarillo("\tNo hay incidencias válidas: no se guarda ni se modifica el JSON."))
    else:
        try:
            guardar_json(validas, args.json)
        except OSError:
            print(rojo(f"\tNo puedo escribir {os.path.basename(args.json)}."))

    # ---- PASO 5 (al final, para que el navegador no se mezcle con las preguntas)
    if html_ok and not args.no_abrir:
        paso(5, "Abrir el informe")
        if abrir_navegador(args.html):
            print(verde("\t✔ Abierto en el navegador."))
        else:
            print(amarillo(f"\tNo he podido abrir el navegador: abre a mano {os.path.basename(args.html)}"))
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\n\tCancelado por el usuario.")