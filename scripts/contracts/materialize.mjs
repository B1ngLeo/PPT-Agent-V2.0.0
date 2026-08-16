import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { generatedOutputs } from "./catalog.mjs";

const root = resolve(import.meta.dirname, "../..");
const checkOnly = process.argv.includes("--check");
const drift = [];

for (const [relativePath, expected] of generatedOutputs()) {
  const target = resolve(root, relativePath);
  if (checkOnly) {
    let actual = null;
    try {
      actual = await readFile(target, "utf8");
    } catch {
      // Missing generated output is reported as drift below.
    }
    if (actual !== expected) drift.push(relativePath);
    continue;
  }
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, expected, "utf8");
}

if (drift.length > 0) {
  console.error("Generated contract files are missing or stale:");
  for (const file of drift) console.error(`- ${file}`);
  console.error("Run: pnpm contracts:materialize");
  process.exit(1);
}

console.log(
  checkOnly
    ? "contract materialization: clean"
    : "contract materialization: updated",
);
