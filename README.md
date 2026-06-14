# Tonight's Menu

A mobile-first party menu and lightweight ordering system. Guests can browse,
search, order one item immediately, or build a basket. The host manages the menu
through a password-protected editor and receives orders through Pushover.

The application is designed to run from a Git-backed Portainer stack behind
Nginx and an existing Cloudflare Tunnel. Menu data and uploaded images are stored
in a persistent Docker volume.

## Features

- Responsive black-and-white guest menu
- Search across item names and descriptions
- Immediate single-item ordering and an optional browser-local basket
- Guest name remembered in a secure cookie; notes are never remembered
- Pushover notifications with the ordered items first and host-only recipes last
- Host login protected by an environment password
- Add, edit, reorder, disable, and delete menu items
- Add, rename, reorder, and remove categories
- Hidden `Unassigned` category for items that should not appear publicly
- Structured recipe ingredients with optional milliliter amounts
- Consistent responsive image crops with a host-selected focal point
- Automatic orientation correction, resizing, and WebP conversion for uploads
- CSV and ZIP bulk imports
- Portable ZIP exports containing the complete menu state and local images

## Application URLs

| Path | Purpose |
| --- | --- |
| `/` | Public menu |
| `/order/item/<id>` | Single-item order form |
| `/order/basket` | Basket checkout |
| `/host` | Host editor; redirects to login when needed |
| `/host/login` | Host login |
| `/health` | Container health endpoint |

## Architecture

```text
Internet
  -> Cloudflare Tunnel
  -> party-menu-nginx:80 on ncleroy-net
  -> Nginx on party-menu-internal
  -> Gunicorn / Flask on menu:8000
  -> SQLite + uploads in menu_data

Flask
  -> party-menu-egress
  -> Pushover Messages API
```

No application port is published on the Docker host. Nginx is reachable by the
Cloudflared container through the external `ncleroy-net` Docker network. The
Flask container can reach the internet only through its separate egress network.

## Environment Variables

The Compose deployment requires the first four variables. Copy `.env.example`
to `.env` only for local Docker Compose use. In Portainer, enter the values in
the stack environment variable section instead.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `ADMIN_PASSWORD` | Production | `change-me-tonight` outside Compose | Password for `/host`. Use a long, unique value. Compose refuses to deploy without it. |
| `SECRET_KEY` | Production | Random on each process start outside Compose | Signs Flask sessions and CSRF tokens. It must remain stable across restarts and replicas. Generate it with `openssl rand -hex 32`. |
| `PUSHOVER_API_TOKEN` | For ordering | Empty outside Compose | Application API token from the Pushover application dashboard. |
| `PUSHOVER_USER_KEY` | For ordering | Empty outside Compose | Pushover user or delivery-group key that receives orders. |
| `DATA_DIR` | No | `./data` locally; `/data` in Docker | Directory containing `menu.db` and `uploads/`. The Compose file sets this to `/data`. |
| `COOKIE_SECURE` | Recommended with HTTPS | `false`; Compose sets `true` | When `true`, host sessions and remembered guest names are sent only over HTTPS. Keep it `true` behind Cloudflare. |
| `PUSHOVER_API_URL` | No | `https://api.pushover.net/1/messages.json` | Override for testing or a compatible proxy. Normally leave unset. |

The current Compose file passes the four required variables and fixes
`DATA_DIR=/data` and `COOKIE_SECURE=true`. To use `PUSHOVER_API_URL` in Docker,
add it to the `menu.environment` section. Direct Python runs read every variable
listed above.

Do not commit real credentials. The repository ignores `.env`, but
`.env.example` is intentionally safe to commit.

### Generate Secrets

```bash
openssl rand -hex 32
```

Use the output as `SECRET_KEY`. A password manager should generate and store the
host password.

## Run Locally with Python

Requirements: Python 3.13 or another supported Python 3 version, `pip`, and a
Pushover account if you want to test ordering.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export ADMIN_PASSWORD='replace-with-a-long-password'
export SECRET_KEY="$(openssl rand -hex 32)"
export PUSHOVER_API_TOKEN='your-application-api-token'
export PUSHOVER_USER_KEY='your-user-or-group-key'

python app.py
```

Open `http://localhost:8000`. For local HTTP, leave `COOKIE_SECURE` unset or set
it to `false`; otherwise the browser will not send the login cookie over HTTP.

## Run Locally with Docker Compose

The Compose file expects the external network used by Cloudflared. Create it once
if it does not already exist:

```bash
docker network create ncleroy-net
cp .env.example .env
```

Edit `.env`, then run:

```bash
docker compose up --build
```

The production Compose file intentionally publishes no host port. Access it
through a Cloudflared container attached to `ncleroy-net`, or temporarily add a
local port mapping to the Nginx service while developing.

## Deploy with Portainer

1. Ensure the external Docker network `ncleroy-net` exists and the Cloudflared
   container is attached to it.
2. In Portainer, open **Stacks**, select **Add stack**, and choose **Repository**.
3. Use this repository URL and set the Compose path to `docker-compose.yml`.
4. Add `ADMIN_PASSWORD`, `SECRET_KEY`, `PUSHOVER_API_TOKEN`, and
   `PUSHOVER_USER_KEY` in the stack environment variables.
5. Deploy the stack and wait for the `menu` health check to pass.
6. In Cloudflare Zero Trust, point the public hostname at:

   ```text
   http://party-menu-nginx:80
   ```

7. Open the public hostname and verify `/`, `/host`, and `/health`.

Nginx configuration is copied into `Dockerfile.nginx` at build time. There is no
host bind mount for `nginx.conf`, avoiding Portainer file-versus-directory mount
errors. Redeploy the stack after changing Nginx configuration.

## Configure Pushover

1. Create an application in Pushover.
2. Copy its API token to `PUSHOVER_API_TOKEN`.
3. Copy your account user key, or a delivery-group key, to `PUSHOVER_USER_KEY`.
4. Redeploy the stack after changing either value.
5. Submit a test order from the public menu.

If either value is missing or rejected, guests see a generic failure message and
the container log records a Pushover warning without exposing credentials.

Orders place the item summary before recipes so lock-screen notifications show
the complete order first. Recipes are never rendered on the public menu.

## Host Workflow

Open `/host` and log in with `ADMIN_PASSWORD`.

- Use **Add item** to create an item, upload its image, select the crop focus, and
  add recipe ingredients.
- Use the item arrows to reorder items inside their category.
- Toggle **Available / Out** without deleting the item.
- Use **Manage categories** to add, rename, reorder, or remove sections.
- When removing a category, move its items, create a replacement category, keep
  them hidden in `Unassigned`, or delete them.
- Use **Full export** before a large edit or bulk replacement.

Uploaded images are validated, EXIF-oriented, limited to 1600 pixels on their
longest side, and stored as WebP. External image URLs are displayed remotely and
are not downloaded or converted.

## Bulk Import and Export

The host editor accepts CSV files and ZIP archives in two modes:

- **Add to current menu** creates missing categories and appends valid items.
- **Replace entire menu** restores the uploaded file as the complete menu state.

Use the downloadable CSV template from the host editor as a starting point. ZIP
imports may include an `images/` directory. Full exports include `menu.csv`,
`categories.csv`, `manifest.json`, and all local images, including built-in menu
images.

See [docs/import-export.md](docs/import-export.md) for the full column reference,
archive layout, validation rules, and restore behavior.

## Data, Backups, and Updates

The named Docker volume `menu_data` contains:

```text
/data/menu.db
/data/uploads/
```

Git redeploys and container recreation do not remove this volume.

Use both backup methods:

1. Download **Full export** from `/host` for a portable application-level backup.
2. Back up `menu_data` for a complete infrastructure-level snapshot.

To roll back menu content, upload a previous full export and select **Replace
entire menu**. This replaces categories, items, ordering, availability, recipes,
crop focus, and local images. It does not change environment variables.

## Security Notes

- Keep the app behind HTTPS and leave `COOKIE_SECURE=true` in production.
- Use unique values for `ADMIN_PASSWORD` and `SECRET_KEY`.
- Never expose the Flask or Nginx container directly unless you intentionally add
  authentication and firewall controls.
- Host mutations and orders are protected by CSRF tokens.
- Sessions are HTTP-only and use `SameSite=Lax`.
- Uploaded files are decoded as images before being stored.
- The app trusts one reverse-proxy hop for forwarded host, protocol, and client IP
  values. Keep it behind the included Nginx proxy.

## Troubleshooting

### Portainer says an environment variable is missing

All four required Compose variables must exist in the stack configuration. Empty
values do not satisfy `${VARIABLE:?message}`.

### Host login works and then immediately expires

Keep `SECRET_KEY` stable across redeploys and replicas. Changing it invalidates
existing sessions.

### Host login does not persist during local HTTP development

Set `COOKIE_SECURE=false`. Secure cookies are intentionally not sent over plain
HTTP.

### Pushover orders fail

Confirm both Pushover values, verify the Flask container has outbound internet
access through `party-menu-egress`, and inspect the `menu` service logs.

### Cloudflare returns a gateway error

Verify Cloudflared and `nginx` are both attached to `ncleroy-net`, and that the
tunnel service is `http://party-menu-nginx:80`.

### An import skips rows

Check required fields, recipe JSON, category names, and referenced image paths.
For ZIP imports, `image_filename` must match the archive path exactly. The result
message reports imported and skipped row counts.

## Development

Run the test suite:

```bash
python -m unittest discover -s tests -v
```

Validate the production Compose file:

```bash
docker compose config --quiet
```

Important files:

| Path | Purpose |
| --- | --- |
| `app.py` | Flask routes, database schema, imports/exports, and Pushover integration |
| `templates/` | Public and host Jinja templates |
| `static/` | CSS, browser JavaScript, and built-in images |
| `docker-compose.yml` | Production services, networks, volume, and health check |
| `Dockerfile` | Flask/Gunicorn image |
| `Dockerfile.nginx` | Nginx image |
| `nginx.conf` | Reverse proxy and 50 MB upload limit |
| `tests/test_app.py` | Application test suite |
