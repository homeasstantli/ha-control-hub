#!/usr/bin/env node
/**
 * Create a one-time pairing code for a hub.
 *
 *   GOOGLE_APPLICATION_CREDENTIALS=./sa.json \
 *   node scripts/create-pairing-code.js <hubId> [ttlMinutes]
 *
 * Or run it from a machine already authenticated with
 * `gcloud auth application-default login` on the project.
 */

const { initializeApp, applicationDefault } = require("firebase-admin/app");
const {
  getFirestore,
  FieldValue,
  Timestamp,
} = require("firebase-admin/firestore");

const hubId = process.argv[2];
const ttlMin = Number(process.argv[3] || 15);

if (!hubId) {
  console.error("usage: node scripts/create-pairing-code.js <hubId> [ttlMinutes]");
  process.exit(1);
}

initializeApp({ credential: applicationDefault() });
const db = getFirestore();

function randomCode() {
  const alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"; // no confusing chars
  const pick = () =>
    Array.from({ length: 4 }, () =>
      alphabet[Math.floor(Math.random() * alphabet.length)]
    ).join("");
  return `${pick()}-${pick()}`;
}

(async () => {
  const code = randomCode();
  await db
    .collection("pairingCodes")
    .doc(code)
    .set({
      hubId,
      used: false,
      createdAt: FieldValue.serverTimestamp(),
      expiresAt: Timestamp.fromMillis(Date.now() + ttlMin * 60 * 1000),
    });
  console.log(`Pairing code for "${hubId}" (expires in ${ttlMin} min): ${code}`);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
