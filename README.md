# Tonight's Menu

A mobile-first party menu with a password-protected host editor. Guests browse the menu; the host can add, edit, reorder, disable, delete, upload, and bulk-import items.

## Features

- Public categories that the host can extend at any time
- Clear `Out` state without removing an item
- Host login controlled by an environment password
- Add new menu categories from the host editor
- Reorder public menu categories from the host editor
- Reorder items within each category
- Single-item image upload or external image URL
- Generated photos for every built-in menu item
- Bulk CSV import with image URLs
- Bulk ZIP import containing `menu.csv` plus local photos
- SQLite database and uploaded images stored in a persistent Docker volume
- Nginx reverse proxy connected to the existing external `ncleroy-net` network

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ADMIN_PASSWORD='choose-a-password'
export SECRET_KEY="$(openssl rand -hex 32)"
python app.py
```

Open `http://localhost:8000`. The editor is at `http://localhost:8000/host`.

## Bulk import

Download the CSV template from the editor. Required columns are `name` and `category`. Optional columns are `description`, `available`, `image_url`, and `image_filename`.

For many local photos, upload a ZIP like this:

```text
party-menu.zip
├── menu.csv
└── images/
    ├── negroni.jpg
    └── cheese-board.png
```

Reference those files as `images/negroni.jpg` and `images/cheese-board.png` in the CSV's `image_filename` column.

## Deploy with Portainer

1. Push this directory to a Git repository.
2. In Portainer, choose **Stacks → Add stack → Repository**.
3. Enter the repository URL and use `docker-compose.yml` as the compose path.
4. Add these environment variables:

```text
ADMIN_PASSWORD=<a long host password>
SECRET_KEY=<output of: openssl rand -hex 32>
```

5. Deploy the stack.
6. In the existing Cloudflare Zero Trust tunnel, set the public hostname service to `http://party-menu-nginx:80`.

The existing Cloudflared container and this stack must both be attached to the external Docker network `ncleroy-net`. The stack gives Nginx the stable network alias `party-menu-nginx`; the Flask app itself remains isolated on a private internal network.

Both application images are built directly from the Git checkout. Nginx configuration is copied into its image during the build, so Portainer does not need to create a host file bind mount.

The named volume `menu_data` keeps the menu database and uploaded photos across Git redeploys. No application port is published directly on the Docker host.

## Back up the menu

Back up the Docker volume `menu_data`. It contains both `/data/menu.db` and `/data/uploads/`.

## Tests

```bash
python -m unittest discover -s tests -v
```
