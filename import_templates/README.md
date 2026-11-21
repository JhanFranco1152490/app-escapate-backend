# Plantillas de carga inicial (CSV)

Plantillas de `uv run python -m app.cli import-csv`, con datos inventados. Cada columna es un
campo del alta de la API, con el mismo nombre y las mismas reglas.

- Separador `;` o `,` (se reconoce solo) y codificación UTF-8 ("CSV UTF-8" al guardar desde
  Excel).
- Celda vacía = campo sin valor. Una columna con un nombre que el sistema no conoce detiene
  la carga antes de guardar nada.
- Fechas `AAAA-MM-DD`. Listas en una celda separadas por `|` (`ground|tours`). Sí/no como
  `sí`, `no`, `true`, `false`, `1`, `0` o `x`.
- Valores de las listas fijas, en inglés como en la API: `client_type` (`person`, `company`),
  `contact_source` (`instagram`, `facebook`, `whatsapp`, `google`, `referral`, `walk_in`,
  `other`, que pide `contact_source_detail`) y `categories` (`lodging`, `air`, `ground`,
  `tours`, `cruise`, `food`, `wholesaler`, `other`).
- `data_consent` (clientes) es obligatoria: confirma que el cliente autorizó el tratamiento de
  sus datos; queda registrada a nombre de la cuenta de `--as`.

Primero se prueba sin guardar y después se carga:

```bash
uv run python -m app.cli import-csv clients clientes.csv --as admin@ejemplo.com --dry-run
uv run python -m app.cli import-csv clients clientes.csv --as admin@ejemplo.com
```

El informe lista las filas omitidas (documento ya registrado) y las que tienen errores, con
su número de fila en la hoja y el campo, sin repetir los datos de la persona. Las filas
buenas se guardan aunque otras fallen; se corrigen las que fallaron y se vuelve a correr: las
que ya entraron se omiten.
