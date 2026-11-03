import csv
import xml.etree.ElementTree as ET
import xml.dom.minidom

FITXER_CSV = "incidencies.csv"
CAMPS = ["data", "reportat_per", "departament", "planta", "equip",
         "tipus", "prioritat", "descripcio", "usuaris_afectats", "causa"]

arrel = ET.Element("incidencies")

with open(FITXER_CSV, newline="", encoding="utf-8") as f:
    lector = csv.reader(f)
    next(lector)                          # salta la fila de cabeceras
    for num, fila in enumerate(lector, start=1):
        if not any(c.strip() for c in fila):
            continue                      # salta filas vacías
        id_ = fila[11].strip() if len(fila) > 11 and fila[11].strip() else f"G8-{num:04d}"
        inc = ET.SubElement(arrel, "incidencia", id=id_)
        for camp, valor in zip(CAMPS, fila[1:11]):    # fila[0] es la marca de temps
            ET.SubElement(inc, camp).text = valor.strip()

text = xml.dom.minidom.parseString(ET.tostring(arrel, encoding="utf-8")).toprettyxml(indent="  ", encoding="utf-8")
with open("incidencies.xml", "wb") as f:
    f.write(text)
print("Fet:", len(arrel), "incidencies a incidencies.xml")