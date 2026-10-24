<img src="assets/logo.svg" alt="Control Hub" height="64">

[![Validate](https://github.com/homeasstantli/ha-control-hub/actions/workflows/validate.yml/badge.svg)](https://github.com/homeasstantli/ha-control-hub/actions/workflows/validate.yml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)

A custom [Home Assistant](https://www.home-assistant.io/) integration, installable
through [HACS](https://hacs.xyz/), that connects your instance to a **Firebase**
project used as a configuration and data store.

* **No cost** — stays on Firebase's free **Spark plan**. No Cloud Functions, no
  billing account.
* **No service-account keys** in Home Assistant. It signs in with **Anonymous
  Auth** and claims a *hub key* by writing its anonymous uid; security rules do
  the rest.
* Uses **both Cloud Firestore and the Realtime Database**.

The **hub key** is a long random string you pick (12+ chars). Treat it like an
API token: whoever holds it, and claims it first, owns that hub's data.

```
┌────────────────┐  accounts:signUp (anonymous)   ┌─────────────────────┐
│ Home Assistant │ ─────────────────────────────▶ │  Firebase Auth      │
│  (config flow) │ ◀───────────── idToken/refresh │  (free)             │
└──────┬─────────┘                                └─────────────────────┘
       │ claim: write uid to hubs/{key}
       ▼
┌───────────────────────────────────────────────────────────────────────┐
│  Firestore  hubs/{key}/data/config     RTDB  hubs/{key}/state          │
│  security rules: read/write only where hubs/{key}/uid == your uid      │
└───────────────────────────────────────────────────────────────────────┘
```

## Repository layout

```
custom_components/control_hub/   The Home Assistant integration
docs/                            Static control website (copy into config/www/)
assets/                          Logo / icon (SVG)
firebase/                        Security rules for Firestore + the RTDB
  firestore.rules
  database.rules.json
  firebase.json / .firebaserc
.github/workflows/               hassfest + HACS validation, release zipper
```

The integration has two independent halves:

* **Firebase side** (Parts 1–2) — Firestore/RTDB as a config & data store.
* **Local control website** (Part 3) — a GitHub Pages page that talks straight
  to your Home Assistant API over the local network, paired with a one-time
  code. Needs no Firebase.

## Part 1 — Firebase setup (free)

1. In the [Firebase console](https://console.firebase.google.com/), create a
   project (or use an existing one) and add a **Web app** to get its config.
2. **Authentication → Sign-in method → Anonymous → Enable.**
3. Create **Cloud Firestore** (production mode) and a **Realtime Database**.
4. Deploy the security rules from this repo:

   ```bash
   cd firebase
   firebase use <your-project-id>
   firebase deploy --only firestore:rules,database
   ```

That's it — no functions to deploy. Note these three values from the Web app
config (Project settings → General, or `firebase apps:sdkconfig WEB`):

| Field                | Example                                            |
| -------------------- | -------------------------------------------------- |
| Project ID           | `ha-github`                                        |
| Web API key          | `AIza...`                                          |
| Realtime Database URL | `https://<project>-default-rtdb.firebaseio.com`   |

## Part 2 — Install in Home Assistant (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/homeasstantli/ha-control-hub`
   with category **Integration**.
2. Install **Control Hub**, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Control Hub**.
4. Enter the **Project ID**, **Web API key**, **Realtime Database URL**, and a
   **hub key**. Generate a key with e.g. `openssl rand -hex 12`. Use the *same*
   key in your app/site so both sides read the same data.

On submit, Home Assistant creates an anonymous user, writes
`hubs/<key> = { valid: true, uid: <that user> }`, and from then on only that
user can touch `hubs/<key>/**`.

## Part 3 — Local control website

A static page (`docs/index.html`) that controls your **lights and switches**
by talking directly to Home Assistant's REST API. No cloud, no Firebase.

### Recommended: host it from Home Assistant's own `www` folder

Home Assistant serves anything in `/config/www/` at `http://<your-ha>/local/`.
Hosting the page there makes it **same-origin** with the API — no CORS
configuration and no mixed-content problem, because the page and the API share
the same host, port and protocol.

1. Copy `docs/index.html` to `/config/www/control_hub/index.html` (File editor,
   Samba, or SSH — however you normally manage `/config`).
2. Open `http://<your-ha-ip-or-hostname>:8123/local/control_hub/`. The
   "Home Assistant URL" field is prefilled to the page's own address — leave
   it as is.
3. **Developer Tools → Actions →** run `control_hub.create_pairing_code` to
   get an 8-character code (valid 5 minutes, single use), enter it, **Pair**.

That's it — no `configuration.yaml` changes needed for this path. The page
works from any device on your network that can reach Home Assistant (phone,
tablet, another computer) at that same `/local/control_hub/` URL.

### Alternative: GitHub Pages

Hosting the same file externally (`https://homeasstantli.github.io/ha-control-hub/`,
via **Settings → Pages → Source: `main` / `/docs`**) works too, but the page
and HA are then different origins:

* **CORS** — add the Pages origin to `configuration.yaml` and restart HA:

  ```yaml
  http:
    cors_allowed_origins:
      - https://homeasstantli.github.io
  ```

* **Mixed content** — a page served over `https://` (GitHub Pages) cannot call
  a plain `http://homeassistant.local:8123`; you'd need Home Assistant behind
  HTTPS (reverse proxy / Nabu Casa) to pair from the public URL. The `/local/`
  method above avoids this entirely, so it's the one to use unless you
  specifically want the page reachable from outside your network.

### One-time pairing, either way

The token belongs to a dedicated non-admin **"Control Hub Web"** user
(auto-created on first use). Revoke access any time from that user's page in
**Settings → People**, or from its token list.

## Data model

| Location                                  | Purpose                              |
| ----------------------------------------- | ----------------------------------- |
| `hubs/{key}/data/config` (Firestore)      | Config document the hub reads       |
| `hubs/{key}/state`       (RTDB)           | State node the hub reads            |
| `hubs/{key}/uid` / `valid`                | Ownership claim (managed by HA)     |

Poll interval is 5 minutes. Paths are configurable in the setup form
(`{hub_key}` is substituted).

### Entities

| Entity                          | Description                                     |
| ------------------------------- | ---------------------------------------------- |
| `sensor.control_hub_config_keys`| Number of keys in the Firestore config doc     |
| `sensor.control_hub_last_sync`  | `updated` field from the RTDB state node       |
| `binary_sensor.control_hub_connected` | Last sync succeeded                     |

### Services

* **`control_hub.create_pairing_code`** — mint a one-time code for the local
  control website (returns response data; no Firebase needed).
* **`control_hub.set_config`** — merge fields into the Firestore config document
  (`path` optional, defaults to the hub's config doc).
* **`control_hub.push_data`** — write to `rtdb` (append with generated key) or
  `firestore` (merge) at an explicit `path` under `hubs/{key}/…`.

## Security notes

* Anyone with the hub key who claims it *before you do* owns that data. Pick a
  high-entropy key and configure Home Assistant before sharing it.
* Anonymous users are cheap and disposable; deleting the config entry orphans
  the claim. To hand a hub to a new user, clear `hubs/{key}/uid` in the console.
* Rules allow self-service creation of `hubs/{key}` so no admin script is
  needed. Tighten `firestore.rules` / `database.rules.json` (pre-provision keys,
  require `valid`) if you want a closed system.

## Development

CI runs `home-assistant/actions/hassfest` and `hacs/action` on every push.
Publishing a GitHub release named `vX.Y.Z` stamps the manifest version and
attaches `control_hub.zip`.

## License

[MIT](LICENSE)
