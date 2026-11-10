import csv
import os
import sys
import xml.etree.ElementTree as ET
import xml.dom.minidom

FITXER_CSV = "incidencies.csv"
FITXER_XML = "incidencies.xml"
CAMPS = ["data", "reportat_per", "departament", "planta", "equip",
         "tipus", "prioritat", "descripcio", "usuaris_afectats", "causa"]

if not os.path.exists(FITXER_CSV):
    sys.exit("No trobo el fitxer " + FITXER_CSV)

# Si el XML ja existeix, preguntem abans de tocar-lo
if os.path.exists(FITXER_XML):
    print("El fitxer", FITXER_XML, "ja existeix.")
    try:
        resposta = input("Vols sobreescriure'l? (s/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        sys.exit("\nCancel·lat: no s'ha modificat res.")
    if resposta not in ("s", "si", "sí", "y", "yes"):
        sys.exit("No s'ha modificat res. Es conserva l'XML existent.")

arrel = ET.Element("incidencies")

try:
    with open(FITXER_CSV, newline="", encoding="utf-8") as f:
        lector = csv.reader(f)
        try:
            next(lector)                      # salta la fila de cabeceras
        except StopIteration:
            sys.exit("El fitxer " + FITXER_CSV + " està buit.")
        for num, fila in enumerate(lector, start=1):
            if not any(c.strip() for c in fila):
                continue                      # salta filas vacias
            id_ = fila[11].strip() if len(fila) > 11 and fila[11].strip() else f"G8-{num:04d}"
            inc = ET.SubElement(arrel, "incidencia", id=id_)
            for camp, valor in zip(CAMPS, fila[1:11]):    # fila[0] es la marca de temps
                ET.SubElement(inc, camp).text = valor.strip()
except UnicodeDecodeError:
    sys.exit("No puc llegir " + FITXER_CSV + ": no està en UTF-8.")
except (csv.Error, OSError):
    sys.exit("No puc llegir " + FITXER_CSV + ".")

if len(arrel) == 0:
    sys.exit("El fitxer " + FITXER_CSV + " no té cap incidència.")

try:
    text = xml.dom.minidom.parseString(ET.tostring(arrel, encoding="utf-8")).toprettyxml(indent="  ", encoding="utf-8")
    with open(FITXER_XML, "wb") as f:
        f.write(text)
except OSError:
    sys.exit("No puc escriure " + FITXER_XML + ".")
print("Fet:", len(arrel), "incidencies a", FITXER_XML)