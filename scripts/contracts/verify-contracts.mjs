import { readFile, readdir } from "node:fs/promises";
import { resolve } from "node:path";
import SwaggerParser from "@apidevtools/swagger-parser";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import YAML from "yaml";
import { endpoints, schemas } from "./catalog.mjs";

const root = resolve(import.meta.dirname, "../..");
const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);

for (const value of Object.values(schemas)) ajv.addSchema(value);

let verifiedFixtures = 0;
for (const [name, value] of Object.entries(schemas)) {
  const validate = ajv.getSchema(value.$id);
  const valid = JSON.parse(
    await readFile(
      resolve(root, `packages/contracts/fixtures/schemas/${name}.valid.json`),
      "utf8",
    ),
  );
  const invalid = JSON.parse(
    await readFile(
      resolve(root, `packages/contracts/fixtures/schemas/${name}.invalid.json`),
      "utf8",
    ),
  );
  if (!validate(valid))
    throw new Error(
      `${name} valid fixture failed: ${ajv.errorsText(validate.errors)}`,
    );
  if (validate(invalid))
    throw new Error(`${name} invalid fixture unexpectedly passed`);
  verifiedFixtures += 2;
}

const openApiPath = resolve(root, "packages/contracts/openapi.yaml");
await SwaggerParser.validate(openApiPath);
const openApi = YAML.parse(await readFile(openApiPath, "utf8"));
const operationIds = new Set();
for (const pathItem of Object.values(openApi.paths)) {
  for (const [method, operation] of Object.entries(pathItem)) {
    if (!["get", "post", "patch", "delete", "put"].includes(method)) continue;
    if (operationIds.has(operation.operationId))
      throw new Error(`Duplicate operationId: ${operation.operationId}`);
    operationIds.add(operation.operationId);
  }
}

const mutationValidator = ajv.compile({
  ...openApi.components.schemas.MutationRequest,
  $schema: "https://json-schema.org/draft/2020-12/schema",
});
const responseValidator = ajv.compile({
  ...openApi.components.schemas.ResourceResponse,
  $schema: "https://json-schema.org/draft/2020-12/schema",
});
const problemValidator = ajv.getSchema(schemas.ProblemDetails.$id);
for (const endpoint of endpoints) {
  if (!operationIds.has(endpoint.operationId))
    throw new Error(`OpenAPI missing operation ${endpoint.operationId}`);
  const fixture = JSON.parse(
    await readFile(
      resolve(
        root,
        `packages/contracts/fixtures/endpoints/${endpoint.operationId}.json`,
      ),
      "utf8",
    ),
  );
  if (fixture.operationId !== endpoint.operationId)
    throw new Error(`Fixture operation mismatch: ${endpoint.operationId}`);
  if (fixture.request.method !== endpoint.method.toUpperCase())
    throw new Error(`Fixture method mismatch: ${endpoint.operationId}`);
  if (endpoint.method !== "get" && !mutationValidator(fixture.request.body))
    throw new Error(
      `Request fixture invalid: ${endpoint.operationId}: ${ajv.errorsText(mutationValidator.errors)}`,
    );
  if (!responseValidator(fixture.response.body))
    throw new Error(
      `Response fixture invalid: ${endpoint.operationId}: ${ajv.errorsText(responseValidator.errors)}`,
    );
  if (!problemValidator(fixture.error))
    throw new Error(
      `Error fixture invalid: ${endpoint.operationId}: ${ajv.errorsText(problemValidator.errors)}`,
    );
  verifiedFixtures += 3;
}

const machines = JSON.parse(
  await readFile(
    resolve(root, "packages/contracts/state-machines.json"),
    "utf8",
  ),
);
for (const [name, machine] of Object.entries(machines.machines)) {
  if (!(machine.initial in machine.transitions))
    throw new Error(`${name}: initial state is undefined`);
  for (const terminal of machine.terminal) {
    if (!(terminal in machine.transitions))
      throw new Error(`${name}: terminal state is undefined: ${terminal}`);
    if (machine.transitions[terminal].length > 0)
      throw new Error(
        `${name}: terminal state has outgoing transitions: ${terminal}`,
      );
  }
  for (const [from, targets] of Object.entries(machine.transitions)) {
    for (const target of targets)
      if (!(target in machine.transitions))
        throw new Error(`${name}: ${from} targets undefined ${target}`);
  }
}

const jobStates = new Set(Object.keys(machines.machines.job.transitions));
for (const [event, status] of Object.entries(machines.jobEventStatusMap)) {
  if (!jobStates.has(status))
    throw new Error(`Event ${event} maps to undefined job status ${status}`);
}
if (
  machines.logicalTaskKey.includes("attempt") ||
  !machines.executionMetadataExcludedFromLogicalKey.includes("attempt")
) {
  throw new Error("attempt must be excluded from the logical idempotency key");
}

const required = JSON.parse(
  await readFile(
    resolve(root, "packages/contracts/required-contracts.json"),
    "utf8",
  ),
);
for (const [goal, needs] of Object.entries(required.goals)) {
  for (const name of needs.schemas)
    if (!(name in schemas))
      throw new Error(`${goal}: undefined schema ${name}`);
  for (const operationId of needs.endpoints)
    if (!operationIds.has(operationId))
      throw new Error(`${goal}: undefined endpoint ${operationId}`);
}

const endpointFixtureCount = (
  await readdir(resolve(root, "packages/contracts/fixtures/endpoints"))
).filter((name) => name.endsWith(".json")).length;
if (endpointFixtureCount !== endpoints.length)
  throw new Error(
    `Expected ${endpoints.length} endpoint fixtures, found ${endpointFixtureCount}`,
  );

console.log(
  `contracts: ${Object.keys(schemas).length} schemas, ${endpoints.length} endpoints, ${verifiedFixtures} positive/negative/request/response/error fixtures`,
);
console.log(
  "contracts: OpenAPI, state machines, event mappings, error model, and Goal prerequisites verified",
);
