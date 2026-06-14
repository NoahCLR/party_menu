# Import and Export Reference

The host editor supports portable menu backups and bulk item creation. Open
`/host`, select **Bulk import**, and upload either a CSV file or a ZIP archive.

## Import Modes

### Add to current menu

- Keeps every existing category and item.
- Creates valid categories that do not already exist.
- Appends imported items after existing items in each category.
- Uses `sort_order` to determine the order of imported rows within a category.
- Uses `category_order` to determine the relative order of newly created
  categories; new categories are still placed after existing categories.
- Skips invalid rows and reports the number skipped.
- Resizes and converts valid bundled images to WebP.

A missing or invalid bundled image makes that row invalid. Other valid rows in
the same import continue.

### Replace entire menu

- Validates the complete archive before deleting the current menu.
- Replaces categories, including empty categories.
- Replaces all items and their order, availability, descriptions, recipes,
  images, and focal points.
- Restores hidden `Unassigned` items without exposing them publicly.
- Fails the complete restore if a referenced bundled image is missing or invalid.
- Leaves the current menu intact if validation or image processing fails.

Use this mode to restore a ZIP created by **Full export**.

## CSV Columns

The file must use UTF-8 encoding. Header names are case-insensitive and leading
or trailing whitespace in headers is ignored.

| Column | Required | Accepted value |
| --- | --- | --- |
| `name` | Yes | Item name. Blank names are invalid. |
| `category` | Yes | Existing or new category name. `Unassigned` keeps the item hidden. |
| `description` | No | Public item description. |
| `available` | No | `yes`, `true`, or `1` for available; `no`, `false`, `0`, `out`, or `sold out` for unavailable. Blank defaults to available. |
| `image_url` | No | An `http://` or `https://` image URL. The server does not download or convert it. |
| `image_filename` | No | Path to an image inside the uploaded ZIP, such as `images/negroni.jpg`. This takes precedence over `image_url` when the file exists. |
| `image_focus_x` | No | Horizontal crop focus from `0` (left) to `100` (right). Defaults to `50`. |
| `image_focus_y` | No | Vertical crop focus from `0` (top) to `100` (bottom). Defaults to `50`. |
| `category_order` | No | Integer category position. Used fully during replacement and relatively for new categories during add mode. |
| `sort_order` | No | Integer item position within its category. |
| `recipe` | No | JSON array of ingredient objects. Defaults to `[]`. |

## Recipe Format

Recipes are host-only and are appended to Pushover orders after the item summary.
Each ingredient has a `name` and an optional `ml` value.

```json
[
  {"name": "Vodka", "ml": "40"},
  {"name": "Espresso", "ml": "30"},
  {"name": "Coffee liqueur", "ml": "20"},
  {"name": "Ice", "ml": ""}
]
```

Rules:

- At most 20 ingredients per item.
- Ingredient names may contain at most 80 characters.
- `ml` may be blank for non-liquid ingredients.
- A supplied amount must be positive, no greater than `10000`, and have at most
  two decimal places.

Because CSV fields containing JSON include commas and quotation marks, use a CSV
writer or spreadsheet export instead of manually joining values with commas.

## CSV Example

```csv
name,description,category,available,image_url,image_filename,image_focus_x,image_focus_y,category_order,sort_order,recipe
Espresso Martini,"Vodka, espresso, and coffee liqueur.",Cocktails,yes,,images/espresso-martini.jpg,50,40,1,1,"[{""name"":""Vodka"",""ml"":""40""}]"
Sparkling Water,Cold and fizzy.,Soft Drinks,yes,https://example.com/water.jpg,,50,50,2,1,[]
```

The host editor provides a downloadable template with the current column order.

## ZIP Layout

For add mode, the ZIP needs a CSV file. A file named `menu.csv` is preferred.

```text
party-menu.zip
|-- menu.csv
`-- images/
    |-- espresso-martini.jpg
    `-- cheese-board.png
```

Reference each image using its full archive path in `image_filename`.

Full exports have this layout:

```text
party-menu-export-YYYYMMDD-HHMMSS.zip
|-- menu.csv
|-- categories.csv
|-- manifest.json
`-- images/
    `-- <item-id>-<image-name>
```

`categories.csv` preserves empty categories and exact category ordering.
`manifest.json` identifies the archive format and records the export timestamp.

## Image Processing

Bundled JPG, JPEG, PNG, WebP, and GIF files are accepted. Each source image must
be no larger than 10 MB and 40 million pixels. The server:

1. Decodes and validates the image.
2. Applies EXIF orientation.
3. Reduces the longest side to at most 1600 pixels.
4. Encodes the result as WebP.
5. Stores the selected focal coordinates separately.

Animated GIFs are imported from their first frame. Remote `image_url` images are
not fetched, validated, or included in exports.

## Limits

- HTTP upload body: 50 MB.
- Extracted ZIP contents: 200 MB.
- CSV inside a ZIP: 5 MB.
- `categories.csv`: 1 MB.
- Individual bundled image: 10 MB.

## Backup and Restore Procedure

Before a large change:

1. Open `/host`.
2. Select **Full export**.
3. Store the ZIP somewhere outside the Docker host.
4. Make the menu changes.

To restore:

1. Open **Bulk import**.
2. Select the previous export ZIP.
3. Choose **Replace entire menu**.
4. Confirm the destructive action.
5. Verify categories, availability, images, recipes, and item ordering.

The export does not contain environment variables, Pushover credentials, login
secrets, guest cookies, or historical orders.
