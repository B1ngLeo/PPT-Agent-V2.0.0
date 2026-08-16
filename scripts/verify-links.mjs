import { readFile, readdir } from "node:fs/promises";
import { dirname, extname, resolve } from "node:path";
import { existsSync } from "node:fs";

const root = resolve(import.meta.dirname, "..");
// Vendored Markdown is immutable and may link to upstream repository paths
// outside the sparse subtree. Its integrity is covered by verify_vendor.py.
const excluded = new Set([
  ".git",
  ".next",
  ".tmp",
  ".venv",
  "node_modules",
  "vendor",
]);

async function walk(directory) {
  const results = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (excluded.has(entry.name)) continue;
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) results.push(...(await walk(path)));
    else if (extname(entry.name).toLowerCase() === ".md") results.push(path);
  }
  return results;
}

const broken = [];
for (const file of await walk(root)) {
  const text = await readFile(file, "utf8");
  for (const match of text.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
    let target = match[1].trim().replace(/^<|>$/g, "");
    if (/^(https?:|mailto:|#)/i.test(target)) continue;
    target = decodeURIComponent(target.split("#", 1)[0]);
    if (!target) continue;
    if (!existsSync(resolve(dirname(file), target)))
      broken.push(`${file}: ${match[1]}`);
  }
}

if (broken.length > 0) {
  console.error("Broken local Markdown links:");
  broken.forEach((entry) => console.error(`- ${entry}`));
  process.exit(1);
}

console.log("markdown links: all local targets exist");
