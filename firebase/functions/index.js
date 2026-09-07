/**
 * Control Hub - pairing Cloud Function.
 *
 * The Home Assistant config flow POSTs { code } to `redeemPairingCode`.
 * We look the code up in Firestore (`pairingCodes/{code}`), and if it is valid
 * and unused we:
 *   1. mark it consumed,
 *   2. mint a Firebase custom token whose uid == hubId,
 *   3. return the token plus the project config HA needs.
 *
 * Create codes however you like from your app / an admin script, e.g.:
 *   db.collection("pairingCodes").doc("ABCD-1234").set({
 *     hubId: "kitchen-hub",
 *     createdAt: FieldValue.serverTimestamp(),
 *     expiresAt: Timestamp.fromMillis(Date.now() + 15 * 60 * 1000),
 *     used: false,
 *   });
 */

const { onRequest } = require("firebase-functions/v2/https");
const { initializeApp } = require("firebase-admin/app");
const { getFirestore, FieldValue } = require("firebase-admin/firestore");
const { getAuth } = require("firebase-admin/auth");

initializeApp();
const db = getFirestore();

// Filled in at deploy time via env; falls back to project defaults.
const PROJECT_ID = process.env.GCLOUD_PROJECT;
const API_KEY = process.env.CONTROL_HUB_WEB_API_KEY || "";
const DATABASE_URL =
  process.env.CONTROL_HUB_DATABASE_URL ||
  `https://${PROJECT_ID}-default-rtdb.firebaseio.com`;

exports.redeemPairingCode = onRequest(
  { cors: true, region: "us-central1" },
  async (req, res) => {
    if (req.method !== "POST") {
      res.status(405).json({ error: "method_not_allowed" });
      return;
    }

    const code = String((req.body && req.body.code) || "").trim();
    if (!code) {
      res.status(400).json({ error: "missing_code" });
      return;
    }

    const ref = db.collection("pairingCodes").doc(code);

    let hubId;
    try {
      hubId = await db.runTransaction(async (tx) => {
        const snap = await tx.get(ref);
        if (!snap.exists) throw new Error("invalid_code");

        const data = snap.data();
        if (data.used) throw new Error("code_used");
        if (
          data.expiresAt &&
          data.expiresAt.toMillis &&
          data.expiresAt.toMillis() < Date.now()
        ) {
          throw new Error("code_expired");
        }

        tx.update(ref, {
          used: true,
          usedAt: FieldValue.serverTimestamp(),
        });
        return data.hubId;
      });
    } catch (err) {
      const known = ["invalid_code", "code_used", "code_expired"];
      const message = known.includes(err.message) ? err.message : "server_error";
      res.status(message === "server_error" ? 500 : 400).json({ error: message });
      return;
    }

    if (!API_KEY) {
      res.status(500).json({ error: "web_api_key_not_configured" });
      return;
    }

    const token = await getAuth().createCustomToken(hubId, { hub: true });

    res.status(200).json({
      hubId,
      projectId: PROJECT_ID,
      apiKey: API_KEY,
      databaseURL: DATABASE_URL,
      token,
    });
  }
);
