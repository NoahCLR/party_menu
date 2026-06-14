# Tonight's Menu

A mobile-first party menu with a password-protected host editor. Guests browse the menu; the host can add, edit, reorder, disable, delete, upload, and bulk-import items.

## Features

- Public categories that the host can extend at any time
- Guest menu search across item names and descriptions
- Clear `Out` state without removing an item
- Fast single-item ordering plus an optional browser-local basket for one combined Pushover order
- Host-only structured recipes appended after the order summary in Pushover notifications
- Guest names remembered for future order forms without saving order notes
- Host login controlled by an environment password
- Add, rename, reorder, and remove public menu categories while deleting, moving, or hiding their items
- Hidden `Unassigned` holding area for items that should remain editable but disappear from the guest menu
- Reorder items within each category
- Single-item image upload or external image URL
- Per-item image focal points with consistent responsive cropping
- Automatic resize, orientation correction, and WebP conversion for local uploads
- Generated photos for every built-in menu item
- Bulk CSV import with image URLs
- Full ZIP export and restore, including categories, item order, availability, and local photos
- SQLite database and uploaded images stored in a persistent Docker volume
- Nginx reverse proxy connected to the existing external `ncleroy-net` network

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ADMIN_PASSWORD='choose-a-password'
export SECRET_KEY="$(openssl rand -hex 32)"
export PUSHOVER_API_TOKEN='your-application-api-token'
export PUSHOVER_USER_KEY='your-user-or-group-key'
python app.py
```

Open `http://localhost:8000`. The editor is at `http://localhost:8000/host`.

## Bulk import

Download the CSV template from the editor. Required columns are `name` and `category`. Optional columns are `description`, `available`, `image_url`, `image_filename`, `image_focus_x`, `image_focus_y`, `category_order`, `sort_order`, and `recipe`. Focus values range from `0` to `100`. The `recipe` column contains a JSON list of ingredient objects with `name` and optional `ml` values; the template includes an example.

For many local photos, upload a ZIP like this:

```text
party-menu.zip
├── menu.csv
└── images/
    ├── negroni.jpg
    └── cheese-board.png
```

Reference those files as `images/negroni.jpg` and `images/cheese-board.png` in the CSV's `image_filename` column.

Choose **Add to current menu** for normal bulk imports. Choose **Replace entire menu** to delete the current menu and restore the uploaded archive as the complete menu state.

Use **Full export** in the host editor before large changes. The downloaded ZIP contains `menu.csv`, `categories.csv`, `manifest.json`, and all local item images. It can be uploaded unchanged with **Replace entire menu**, including empty categories and hidden `Unassigned` items.

## Deploy with Portainer

1. Push this directory to a Git repository.
2. In Portainer, choose **Stacks → Add stack → Repository**.
3. Enter the repository URL and use `docker-compose.yml` as the compose path.
4. Add these environment variables:

```text
ADMIN_PASSWORD=<a long host password>
SECRET_KEY=<output of: openssl rand -hex 32>
PUSHOVER_API_TOKEN=<your Pushover application API token>
PUSHOVER_USER_KEY=<your Pushover user or group key>
```

5. Deploy the stack.
6. In the existing Cloudflare Zero Trust tunnel, set the public hostname service to `http://party-menu-nginx:80`.

Create an application in Pushover to get `PUSHOVER_API_TOKEN`. Your account dashboard provides the separate `PUSHOVER_USER_KEY`; both values are required by the Pushover Messages API.

The existing Cloudflared container and this stack must both be attached to the external Docker network `ncleroy-net`. The stack gives Nginx the stable network alias `party-menu-nginx`. The Flask app receives traffic only through the private internal network and uses a separate bridge network for outbound Pushover API requests.

Both application images are built directly from the Git checkout. Nginx configuration is copied into its image during the build, so Portainer does not need to create a host file bind mount.

The named volume `menu_data` keeps the menu database and uploaded photos across Git redeploys. No application port is published directly on the Docker host.

## Back up the menu

Use **Full export** in the host editor for a portable menu backup that can be restored through bulk import. Also back up the Docker volume `menu_data` for a complete infrastructure-level copy of `/data/menu.db` and `/data/uploads/`.

## Tests

```bash
python -m unittest discover -s tests -v
```
