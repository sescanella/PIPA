---
name: extract-plano
description: Extract all information from a technical drawing PDF (materials, welds, cuts, metadata)
arguments: [pdf_path]
tools: [Bash, Read, Write, Glob]
---

<objective>
Process a complete technical drawing PDF to extract all structured data: materials list, welding list, cutting list, and title block metadata. Generates a single consolidated JSON file.
</objective>

<instructions>

## Step 1: Crop PDF into region images

Run the cropping engine to generate PNG images for each region:

```bash
skills/extract-plano/.venv/bin/python -m src.crop "$ARGUMENTS"
```

> On Windows use `skills/extract-plano/.venv/Scripts/python.exe` instead.

This generates 4 PNG files in `tmp/crops/{pdf_stem}/`:
- `materiales.png` — LISTADO DE MATERIALES table
- `soldaduras.png` — LISTADO DE SOLDADURA table
- `cortes.png` — LISTADO DE CORTES table
- `cajetin.png` — Title block (OT, OF, client, etc.)

Note the `{pdf_stem}` from the output (the PDF filename without extension).

## Step 2: Extract data from each region image

For each of the 4 PNGs, use the Read tool to view the image, then use the Write tool to save the extracted JSON to the same directory.

### 2a. Materiales -> materiales.json

Read `tmp/crops/{stem}/materiales.png`.

Table columns: ITEM, DIAM., CODIGO, DESCRIPCION, CANTIDAD, N COLADA

Extract every data row (skip header and empty rows). JSON array with keys:
- "item": integer (starting from 1)
- "diam": string or null
- "codigo": string or null (alphanumeric code, e.g. "5356516NL1")
- "descripcion": string or null
- "cantidad": string or null (may include units, e.g. "451 MM")
- "n_colada": string or null

Save to `tmp/crops/{stem}/materiales.json`.

### 2b. Soldaduras -> soldaduras.json

Read `tmp/crops/{stem}/soldaduras.png`.

Table columns: N SOLD., DIAM., TIPO SOLD., WPS, FECHA SOLDADURA, SOLDADOR, FECHA INSP. VISUAL, RESULTADO INSP. VISUAL

Extract every data row. JSON array with keys:
- "n_sold": integer
- "diam": string or null
- "tipo_sold": string or null ("SO" = socket weld, "BW" = butt weld)
- "wps": string or null
- "fecha_soldadura": string or null
- "soldador": string or null
- "fecha_insp_visual": string or null
- "resultado_insp_visual": string or null

Save to `tmp/crops/{stem}/soldaduras.json`.

### 2c. Cortes -> cortes.json

Read `tmp/crops/{stem}/cortes.png`.

Table columns: N CORTE, DIAM., LARGO, EXTREMO 1, EXTREMO 2

Extract every data row. JSON array with keys:
- "n_corte": string or null
- "diam": string or null
- "largo": string or null (may include units)
- "extremo1": string or null ("BE" = bevel end, "PE" = plain end)
- "extremo2": string or null

Save to `tmp/crops/{stem}/cortes.json`.

### 2d. Cajetin -> cajetin.json

Read `tmp/crops/{stem}/cajetin.png`.

The cajetin (title block) layout varies between drawings. Scan the entire image for these fields:
- "ot": OT number (format "76400-XXXXXX", labeled "OT:" or "O.T.")
- "of": OF number (numeric, labeled "OF:" or "O.F.")
- "tag_spool": Spool tag/identifier (e.g. "MK-1342-MO-13012-001")
- "diametro_pulgadas": Pipe diameter in inches (e.g. "4\"")
- "cliente": Client name
- "cliente_final": End client name
- "linea": Line designation / pipe line number

Save to `tmp/crops/{stem}/cajetin.json`.

## Step 3: Assemble final JSON

Run the assembler to merge all region JSONs into a validated SpoolRecord:

```bash
skills/extract-plano/.venv/bin/python -m src.assemble "tmp/crops/{stem}"
```

Replace `{stem}` with the actual PDF stem. This validates with Pydantic and saves to `tmp/json/{stem}.json`.

## Step 4: Return result

Output the final JSON path and a summary:
- Number of materials, welds, and cuts found
- OT and OF codes
- Client information
- Any fields that could not be extracted (null values)

</instructions>

<extraction_rules>
- Preserve the EXACT text as shown in each image
- Use null (not empty string) for cells/fields that are empty or unreadable
- Do NOT invent or guess data — only extract what is visible
- If a table appears empty, use an empty array []
- item and n_sold fields should be integers
- All other fields are strings or null
- Date formats should be preserved exactly as shown
</extraction_rules>

<error_handling>

## Error handling

If any step fails, handle it gracefully instead of aborting the entire extraction:

| Failure | Action |
|---------|--------|
| crop.py fails (corrupt PDF, 0 pages) | Return JSON: `{"status": "error", "error": "description", "pdf_name": "file.pdf"}` |
| Vision cannot read a table/region | Use empty array `[]` for that region. Set `"low_confidence": true` in the Step 2 JSON |
| Pydantic ValidationError on a row | assemble.py skips invalid rows automatically. The final JSON will have `"status": "partial"` and `"errors"` listing what was skipped |
| assemble.py fails completely | Return JSON: `{"status": "error", "error": "description", "pdf_name": "file.pdf"}` |

The SpoolRecord includes these optional fields for tracking issues:
- `status`: `"ok"` (all good), `"partial"` (some rows skipped), or `"error"` (total failure)
- `low_confidence`: `true` if any region image could not be read reliably
- `errors`: list of strings describing each issue encountered

Always return a result — even a partial one is more useful than no result.

</error_handling>
