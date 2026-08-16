import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const root = process.cwd();
const schemaDir = path.join(root, "packages", "contracts", "schemas", "v1");
const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);

for (const name of fs
  .readdirSync(schemaDir)
  .filter((entry) => entry.endsWith(".schema.json"))) {
  const schema = JSON.parse(
    fs.readFileSync(path.join(schemaDir, name), "utf8"),
  );
  ajv.addSchema(schema);
}

const validations = [
  ["SourcePackage", "source-package.expected.json"],
  ["DeckPlan", "deck-plan.approved.json"],
];
let checked = 0;
const goldenRoot = path.join(root, "tests", "golden");
for (const caseName of fs.readdirSync(goldenRoot).sort()) {
  const caseRoot = path.join(goldenRoot, caseName);
  if (!fs.statSync(caseRoot).isDirectory()) continue;
  for (const [schemaName, relative] of validations) {
    const validate = ajv.getSchema(
      `https://contracts.instant-ppt.example/v1/${schemaName}.schema.json`,
    );
    const value = JSON.parse(
      fs.readFileSync(path.join(caseRoot, relative), "utf8"),
    );
    if (!validate(value)) {
      throw new Error(
        `${caseName}/${relative}: ${ajv.errorsText(validate.errors)}`,
      );
    }
    checked += 1;
  }
  const render = path.join(caseRoot, "generated", "render");
  for (const [schemaName, relative] of [
    ["QaReport", "qa-report.json"],
    ["ArtifactManifest", "artifact-manifest.json"],
  ]) {
    const validate = ajv.getSchema(
      `https://contracts.instant-ppt.example/v1/${schemaName}.schema.json`,
    );
    const value = JSON.parse(
      fs.readFileSync(path.join(render, relative), "utf8"),
    );
    if (!validate(value)) {
      throw new Error(
        `${caseName}/${relative}: ${ajv.errorsText(validate.errors)}`,
      );
    }
    checked += 1;
  }
}
console.log(
  `golden-contracts: ${checked} artifacts validated against G00 schemas`,
);
