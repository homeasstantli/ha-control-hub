# Control Hub

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
docs/                            Static control website (GitHub Pages)
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

## Part 3 — Local control website (GitHub Pages)

A static page under `docs/` that controls your **lights and switches** by
talking directly to Home Assistant's REST API. No cloud, no Firebase.

### One-time pairing

1. In Home Assistant: **Developer Tools → Actions →** run
   `control_hub.create_pairing_code`. The response contains an 8-character
   `code`, valid **5 minutes**, single use.
2. On the website, enter your Home Assistant URL and the code and press
   **Pair**. The page calls `POST /api/control_hub/pair`, receives a
   long-lived access token, and stores it in the browser's local storage.
3. The token belongs to a dedicated non-admin **"Control Hub Web"** user
   (auto-created). Revoke access any time from that user's page in
   **Settings → People**, or from the token list.

### Enable GitHub Pages

Repo **Settings → Pages → Source: Deploy from a branch → `main` / `/docs`**.
The site is then at `https://homeasstantli.github.io/ha-control-hub/`.

### Make the browser reach Home Assistant

The page and HA are different origins, so:

* **CORS** — add your Pages origin to `configuration.yaml` and restart HA:

  ```yaml
  http:
    cors_allowed_origins:
      - https://homeasstantli.github.io
  ```

* **Mixed content** — a page served over `https://` (GitHub Pages) cannot call
  a plain `http://homeassistant.local:8123`. Your options:
  * Access Home Assistant over HTTPS (reverse proxy / Nabu Casa URL) and use
    that URL when pairing, **or**
  * Run the page locally instead of on Pages:
    `cd docs && python3 -m http.server 8000`, open
    `http://localhost:8000`, and pair with `http://localhost:8123`
    (browsers allow `https`/`localhost` exceptions — and here both are local),
    adding `http://localhost:8000` to `cors_allowed_origins`.

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
