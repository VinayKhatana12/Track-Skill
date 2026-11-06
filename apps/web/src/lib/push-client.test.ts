import { describe, expect, it } from "vitest";

import { urlBase64ToUint8Array } from "./push-client";

/** The conversion helper is exported for tests — it feeds PushManager.subscribe
 * and must round-trip base64url exactly. */
describe("urlBase64ToUint8Array", () => {
  it("decodes a standard VAPID public key (87 chars, 65 bytes)", () => {
    // Deterministic 65-byte uncompressed P-256 point, base64url-encoded.
    const point = Buffer.concat([
      Buffer.from([0x04]),
      Buffer.alloc(64, 0xab),
    ]);
    const base64url = point
      .toString("base64")
      .replaceAll("+", "-")
      .replaceAll("/", "_")
      .replaceAll("=", "");
    const bytes = urlBase64ToUint8Array(base64url);
    expect(bytes).toHaveLength(65);
    expect(bytes[0]).toBe(0x04);
    expect(Array.from(bytes.slice(1, 5))).toEqual([0xab, 0xab, 0xab, 0xab]);
  });

  it("pads missing base64 padding and maps - and _ correctly", () => {
    // "-_-_" -> "+/+/" -> bits 111110 111111 111110 111111
    const bytes = urlBase64ToUint8Array("-_-_");
    expect(Array.from(bytes)).toEqual([0xfb, 0xff, 0xbf]);
  });
});
