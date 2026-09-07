# Control Hub

A Home Assistant integration that pairs your instance to a **Firebase** project
with a one-time **pairing code** and uses **Cloud Firestore** + the **Realtime
Database** as a configuration and data store.

- Pairing-code setup flow (no service-account keys pasted into HA)
- Reads a config document from Firestore and a state node from the RTDB
- `control_hub.set_config` and `control_hub.push_data` services to write back
- Sensors for config size / last sync and a connectivity binary sensor

See the [README](https://github.com/homeasstantli/ha-control-hub) for Firebase setup.
