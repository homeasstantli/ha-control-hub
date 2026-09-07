# Control Hub

[![Validate](https://github.com/homeasstantli/ha-control-hub/actions/workflows/validate.yml/badge.svg)](https://github.com/homeasstantli/ha-control-hub/actions/workflows/validate.yml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)

A custom [Home Assistant](https://www.home-assistant.io/) integration, installable
through [HACS](https://hacs.xyz/), that connects your instance to a **Firebase**
project.

* Setup is done with a **one-time pairing code** — no service-account JSON is
  ever pasted into Home Assistant.
* Firebase is used as a **configuration and data store** (not a live remote
  control channel): the hub reads a config document and a state node, and can
  write back on demand.
* Both **Cloud Firestore** and the **Realtime Database** are supported.

```
┌────────────────┐   pairing code    ┌──────────────────────┐
│ Home Assistant │ ────────────────▶ │ redeemPairingCode    │  Cloud Function
│  (config flow) │ ◀──────────────── │  → Firebase custom    │  (Admin SDK)
└──────┬─────────┘  token + config   │    token + project    │
       │                             └──────────┬───────────┘
       │ signInWithCustomToken                  │
       ▼                                        ▼
  ID token / refresh token           ┌────────────────────────┐
       │                             │  Firestore  +  RTDB     │
       └──────── REST read/write ───▶│  hubs/{hubId}/...       │
                                     └────────────────────────┘
```

## Repository layout

```
custom_components/control_hub/   The Home Assistant integration
firebase/                        Firebase project: rules + pairing Cloud Function
  functions/index.js             redeemPairingCode
  firestore.rules
  database.rules.json
.github/workflows/               hassfest + HACS validation, release zipper
```

## Part 1 — Firebase setup

Prerequisites: a Firebase project with **Cloud Firestore** and the **Realtime
Database** provisioned, and the project on the **Blaze (pay-as-you-go) plan** —
Cloud Functions cannot be deployed on the free Spark plan. Auth needs no sign-in
provider; the function only mints custom tokens.

1. Point the CLI at your project (a `.firebaserc` with `default: ha-github` is
   already committed):

   ```bash
   cd firebase
   firebase use <your-project-id>
   ```

2. Put your Web API key and RTDB URL in `functions/.env` (copy from
   `functions/.env.example`). Get the values with:

   ```bash
   firebase apps:sdkconfig WEB
   ```

   | Variable                   | Value                                           |
   | -------------------------- | ----------------------------------------------- |
   | `CONTROL_HUB_WEB_API_KEY`  | `apiKey` from the SDK config                    |
   | `CONTROL_HUB_DATABASE_URL` | `https://<project>-default-rtdb.firebaseio.com` |

3. Deploy rules, then the function:

   ```bash
   npm --prefix functions install
   firebase deploy --only firestore:rules,database
   firebase deploy --only functions
   ```

4. Create a pairing code. With `gcloud auth application-default login` done, or a
   service-account JSON in `GOOGLE_APPLICATION_CREDENTIALS`:

   ```bash
   node functions/scripts/create-pairing-code.js home-hub 15
   # -> Pairing code for "home-hub" (expires in 15 min): ABCD-EFGH
   ```

After deploy, the function URL is printed — it looks like
`https://us-central1-<project>.cloudfunctions.net/redeemPairingCode` (or a
`run.app` URL for gen-2). That is the **Setup URL** you enter in Home Assistant.

## Part 2 — Install in Home Assistant (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/homeasstantli/ha-control-hub`
   with category **Integration**.
2. Install **Control Hub**, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Control Hub**.
4. Enter the **Setup URL** and **pairing code**. Optionally adjust the Firestore
   and RTDB paths (`{hub_id}` is substituted).

## Data model

| Location                              | Purpose                                  |
| ------------------------------------- | ---------------------------------------- |
| `hubs/{hubId}/config` (Firestore)     | Config document the hub reads each poll  |
| `hubs/{hubId}/state`  (RTDB)          | State node the hub reads each poll       |

Poll interval is 5 minutes.

### Entities

| Entity                          | Description                                     |
| ------------------------------- | ---------------------------------------------- |
| `sensor.control_hub_config_keys`| Number of keys in the Firestore config doc     |
| `sensor.control_hub_last_sync`  | `updated` field from the RTDB state node       |
| `binary_sensor.control_hub_connected` | Last sync succeeded                     |

### Services

* **`control_hub.set_config`** — merge fields into the Firestore config document
  (`path` optional, defaults to the hub's config doc).
* **`control_hub.push_data`** — write to `rtdb` (append with generated key) or
  `firestore` (merge) at an explicit `path`.

## Development

```bash
python -m script.hassfest        # inside a HA checkout, or rely on CI
```

CI runs `home-assistant/actions/hassfest` and `hacs/action` on every push.
Publishing a GitHub release named `vX.Y.Z` stamps the manifest version and
attaches `control_hub.zip`.

## License

[MIT](LICENSE)
