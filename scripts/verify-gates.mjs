import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import YAML from "yaml";

const root = resolve(import.meta.dirname, "..");
const goalArgIndex = process.argv.findIndex((arg) => arg === "--goal");
const inlineGoal = process.argv.find((arg) => arg.startsWith("--goal="));
const goal =
  inlineGoal?.split("=", 2)[1] ??
  (goalArgIndex >= 0 ? process.argv[goalArgIndex + 1] : null);

if (!goal) {
  console.error("Usage: pnpm verify:gates --goal G00");
  process.exit(2);
}

const schema = JSON.parse(
  await readFile(
    resolve(root, "docs/evidence/gate-manifest.schema.json"),
    "utf8",
  ),
);
const manifest = YAML.parse(
  await readFile(resolve(root, "docs/evidence/gate-manifest.yaml"), "utf8"),
);
const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);
const validate = ajv.compile(schema);
if (!validate(manifest)) {
  console.error(ajv.errorsText(validate.errors, { separator: "\n" }));
  process.exit(1);
}

const gates = manifest.gates.filter(
  (gate) => gate.goal === goal && gate.required,
);
if (gates.length === 0) {
  console.error(`No required gates are declared for ${goal}`);
  process.exit(1);
}

const today = new Date();
const blocking = [];
for (const gate of gates) {
  if (gate.status === "passed") continue;
  if (gate.status === "waived") {
    if (!gate.waiver || new Date(gate.waiver.expiresAt) <= today)
      blocking.push(`${gate.id}: waiver missing or expired`);
    continue;
  }
  blocking.push(`${gate.id}: ${gate.status}`);
}

if (blocking.length > 0) {
  console.error(`${goal} required gates are not satisfied:`);
  blocking.forEach((entry) => console.error(`- ${entry}`));
  process.exit(1);
}

console.log(
  `${goal} gates: ${gates.length}/${gates.length} passed or validly waived`,
);
