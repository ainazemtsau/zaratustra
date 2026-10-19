import { readFileSync } from "node:fs";
const config = JSON.parse(
  readFileSync(new URL("../validation.config", import.meta.url)),
);
const result = readFileSync(new URL("../RESULT.md", import.meta.url), "utf8");
for (const key of config.required_fields) {
  if (!new RegExp(`^${key}:\\s*\\S.+`, "m").test(result))
    throw new Error(`Missing/empty RESULT field: ${key}`);
}
if (!/^next: solmax$/m.test(result))
  throw new Error("Return route must be solmax");
console.log(
  "RESULT structure passed (content and owner acceptance require human review).",
);
