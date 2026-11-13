# TA04 · Gestió d'incidències · Grup G8

Projecte de la tasca **TA04 – Programació i Llenguatges de Marques** (mòdul 0373, ASIX · ITB, curs 26/27).

**Grup G8 (ASIXc1B):** Wentao Wu · Ethan Martínez · Jan Peramo

🌐 **Informe web:** <https://USUARI.github.io/ITB2627-MDS/TA04/informe_incidencies.html>
<!-- Substituïu USUARI pel vostre nom d'usuari de GitHub (és la mateixa adreça que mostra el codi QR del programa). -->

---

## Què fa el projecte

Recollim incidències d'equips informàtics i audiovisuals amb un formulari de Google i les convertim en **informació útil**:

```
Google Forms ──► Google Sheets ──► incidencies.csv ──► incidencies.xml ──► filtre + estadístiques ──► incidencies.json
                                                                              │
                                                                              ├─► terminal (colors i barres)
                                                                              └─► informe_incidencies.html (navegador / mòbil amb QR)
```

## Fitxers

| Fitxer | Què és |
|---|---|
| `generar_respostes.gs` | Script de Google Apps Script que omple el formulari automàticament (amb un ~10 % de respostes errònies a propòsit) |
| `incidencies.csv` | Respostes exportades del full de càlcul de Google |
| `csv_a_xml.py` | Converteix `incidencies.csv` a `incidencies.xml` (XML indentat) |
| `incidencies.xml` | Les dades en format XML |
| `gestio_incidencies.py` | Programa principal: llegeix l'XML, filtra, mostra estadístiques, genera l'informe web i desa el JSON |
| `incidencies.json` | Incidències vàlides en format JSON |
| `informe_incidencies.html` | Informe gràfic (el que es publica a GitHub Pages) |

## Requisits

Només **Python 3.8 o superior**. No cal instal·lar cap llibreria: tot fa servir la llibreria estàndard.
Funciona igual a **Windows, macOS i Linux**. Per veure l'informe gràfic n'hi ha prou amb qualsevol navegador.

> A Linux i macOS l'ordre és `python3`; a Windows pot ser `python` o `py`.

## Com s'executa

```bash
python3 csv_a_xml.py            # 1. CSV -> XML
python3 gestio_incidencies.py   # 2. XML -> filtre -> estadístiques -> HTML -> JSON
```

### `csv_a_xml.py`
- Si `incidencies.xml` ja existeix, pregunta si es vol sobreescriure (**només accepta `s` o `n`**).
- Avisa amb un missatge clar si el CSV no existeix, és buit, no és UTF-8 o no té el format esperat.

### `gestio_incidencies.py`
El programa fa cinc passos:

1. **Llegir i filtrar** `incidencies.xml`.
2. **Mostrar a la terminal** les incidències descartades, una taula amb les primeres incidències vàlides i les estadístiques (amb colors, tabuladors i barres).
3. **Generar** `informe_incidencies.html`.
4. **Desar** `incidencies.json`. Si ja existeix, pregunta:
   - `a` → **sobreescriure'l** (esborra el contingut anterior i escriu totes les incidències de nou)
   - `b` → **afegir només les noves** (no repeteix cap incidència amb el mateix ID)
5. **Veure l'informe gràfic**:
   - `1` → **Pantalla**: l'obre al navegador de l'ordinador
   - `2` → **Mòbil**: mostra un **codi QR** a la terminal que porta a la web de GitHub Pages
   - `3` → només terminal

Opcions:

| Opció | Efecte |
|---|---|
| `--sin-web` | Només terminal, no genera l'HTML |
| `--no-abrir` | No pregunta ni obre res al final |
| `--sin-color` | Terminal sense colors |
| `--url https://...` | Adreça de la web per al QR (si no, es calcula sola a partir del repositori) |
| `--xml`, `--json`, `--html` | Altres noms de fitxer |

## Filtre: de dades a informació

Una incidència es **descarta** si:

- la **data** no és vàlida, és **futura** o té **més d'un any** (es calcula amb la data actual, cada vegada que s'executa);
- el **nom de qui reporta** no és vàlid (buit, massa curt o "brossa" com `asdf`);
- el **departament**, la **planta**, l'**equip**, el **tipus**, la **causa** o els **usuaris afectats** no són a les llistes del formulari;
- la **prioritat** no és un número de l'1 al 10;
- la **descripció** és buida o té menys de 10 caràcters;
- l'**ID** és buit o està **duplicat**;
- la combinació és **incoherent** (per exemple, un *switch* amb un problema de *programari*).

## Estadístiques

- Resum: incidències llegides, vàlides, descartades, prioritat mitjana, crítiques (prioritat ≥ 8) i les que afecten més de 5 usuaris.
- Incidències per departament, equip, tipus, planta, causa probable i usuaris afectats.
- Prioritat mitjana per departament i equips amb més incidències crítiques.
- Distribució de la prioritat, dia amb més incidències i recompte per setmanes.
- Top 5 d'incidències més crítiques.

A la terminal, la prioritat es pinta en **vermell** (≥ 8), **groc** (5–7) o **verd** (< 5).

## Informe web i GitHub Pages

`informe_incidencies.html` és un únic fitxer (amb el CSS i el JavaScript a dins, sense dependències d'internet) amb quatre pestanyes: **Resum**, **Incidències vàlides** (amb cerca, filtre per departament, només crítiques, ordenació i paginació), **Descartades** i **Estadístiques**. S'adapta al mòbil i al mode fosc.

Per publicar-lo:

1. Pujar `informe_incidencies.html` al repositori (`git add`, `git commit`, `git push`).
2. A GitHub: **Settings → Pages → Deploy from a branch → main / (root) → Save**.
3. Esperar que a **Actions** surti *pages build and deployment* amb ✔.

> La web mostra l'última versió pujada a GitHub. Si les dades canvien, cal tornar a fer `git push`.

## Control d'errors

Els programes no s'aturen mai amb un *traceback* ni mostren rutes de l'ordinador:

| Cas | Què passa |
|---|---|
| XML inexistent, buit, mal format (per exemple, falta un `<`) o sense incidències | Missatge clar, indicant la línia de l'error |
| Resposta no vàlida a `s/n`, `a/b` o `1/2/3` | Torna a preguntar |
| `Ctrl+C` en qualsevol moment | `Cancel·lat per l'usuari` |
| JSON corrupte | Només deixa l'opció `a` (sobreescriure) |
| Cap incidència vàlida | No toca el JSON i ho avisa |
| Sense permisos per llegir o escriure | Missatge "No puc llegir / escriure…" |
| Executar-lo des d'una altra carpeta | Funciona igual |
| HTML o `<script>` dins les dades | Es mostra com a text a la web, no s'executa |

## Estructura de l'XML

```xml
<incidencies>
  <incidencia id="G8-0001">
    <data>2026-10-03</data>
    <reportat_per>Laia Ferrer</reportat_per>
    <departament>Docència</departament>
    <planta>Pis 2</planta>
    <equip>Switch</equip>
    <tipus>Xarxa</tipus>
    <prioritat>9</prioritat>
    <descripcio>Es perd la xarxa de manera intermitent</descripcio>
    <usuaris_afectats>Més de 20</usuaris_afectats>
    <causa>Desgast o avaria de maquinari</causa>
  </incidencia>
  ...
</incidencies>
```

## Ús de la IA

Hem fet servir la IA com a ajuda per escriure el codi, **sense passar-li mai les dades del formulari**, tal com demana l'enunciat (RGPD).
