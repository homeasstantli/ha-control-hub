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

1. Create a Firebase project and enable **Authentication** (no sign-in provider
   needed — custom tokens only), **Cloud Firestore**, and the **Realtime
   Database**.
2. Grab your **Web API key**: Project settings → General → "Web API Key".
3. Deploy rules and the pairing function:

   ```bash
   cd firebase
   npm --prefix functions install
   firebase use <your-project-id>
   firebase functions:config:set   # (Gen-2) prefer env vars below
   firebase deploy --only firestore:rules,database,functions
   ```

   Set these environment variables for the function (Console → Functions →
   `redeemPairingCode` → Edit, or in `firebase.json` / a `.env` file):

   | Variable                     | Value                                            |
   | ---------------------------- | ------------------------------------------------ |
   | `CONTROL_HUB_WEB_API_KEY`    | your Web API key                                 |
   | `CONTROL_HUB_DATABASE_URL`   | `https://<project>-default-rtdb.firebaseio.com`  |

4. Create a pairing code document (from an admin script or your app):

   ```js
   const { getFirestore, FieldValue, Timestamp } = require("firebase-admin/firestore");
   await getFirestore().collection("pairingCodes").doc("ABCD-1234").set({
     hubId: "home-hub",
     used: false,
     createdAt: FieldValue.serverTimestamp(),
     expiresAt: Timestamp.fromMillis(Date.now() + 15 * 60 * 1000),
   });
   ```

The function's HTTPS URL looks like
`https://us-central1-<project>.cloudfunctions.net/redeemPairingCode` — that is the
**Setup URL** you enter in Home Assistant.

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
