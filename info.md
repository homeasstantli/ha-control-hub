# Control Hub

A Home Assistant integration that connects your instance to a **Firebase**
project used as a configuration and data store — on the **free Spark plan**,
with **no Cloud Functions** and **no service-account keys**.

- Signs in with Firebase **Anonymous Auth** and claims a *hub key* you choose
- Reads a config document from **Cloud Firestore** and a state node from the
  **Realtime Database**
- `control_hub.set_config` and `control_hub.push_data` services to write back
- Sensors for config size / last sync and a connectivity binary sensor

See the [README](https://github.com/homeasstantli/ha-control-hub) for the
one-time Firebase setup (enable Anonymous auth, deploy the security rules).
