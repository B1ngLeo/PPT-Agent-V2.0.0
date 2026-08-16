import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import YAML from "yaml";

const root = resolve(import.meta.dirname, "../..");
const alerts = YAML.parse(
  await readFile(resolve(root, "infra/observability/alerts.yml"), "utf8"),
);
const runbook = await readFile(resolve(root, "docs/runbook.md"), "utf8");
const rules = alerts.groups.flatMap((group) => group.rules);
if (rules.length !== 12) throw new Error(`expected 12 alert rules, got ${rules.length}`);
const runbookAnchors = new Set(
  [...runbook.matchAll(/^## (.+)$/gm)].map((match) =>
    match[1]
      .toLowerCase()
      .replaceAll(/[^a-z0-9]+/g, "-")
      .replaceAll(/^-|-$/g, ""),
  ),
);

const names = new Set();
for (const rule of rules) {
  if (!rule.alert || names.has(rule.alert)) throw new Error("alert names must be unique");
  names.add(rule.alert);
  if (!rule.expr || !["page", "ticket"].includes(rule.labels?.severity)) {
    throw new Error(`${rule.alert}: expression and page/ticket severity are required`);
  }
  const target = rule.annotations?.runbook;
  if (!target?.startsWith("docs/runbook.md#")) {
    throw new Error(`${rule.alert}: repository runbook anchor is required`);
  }
  const heading = target.split("#", 2)[1];
  if (!runbookAnchors.has(heading)) {
    throw new Error(`${rule.alert}: runbook heading is missing`);
  }
}

console.log(`G08 alert rules: ${rules.length}/${rules.length} valid`);
