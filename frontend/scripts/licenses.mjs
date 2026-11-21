// Writes the licenses of the libraries that end up in the build next to it.
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const pkg = JSON.parse(readFileSync("package.json", "utf8"));
const seen = new Set();
const parts = [];

function visit(name) {
  if (seen.has(name)) return;
  seen.add(name);
  const dir = join("node_modules", name);
  const meta = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
  const file = readdirSync(dir).find((f) => /^licen[cs]e/i.test(f));
  const text = file ? readFileSync(join(dir, file), "utf8").trim() : `License: ${meta.license}`;
  parts.push(`${meta.name} ${meta.version} (${meta.license})\n\n${text}`);
  for (const dep of Object.keys(meta.dependencies ?? {})) visit(dep);
}

for (const name of Object.keys(pkg.dependencies ?? {}).sort()) visit(name);
const out = "../src/oslo/web/static/app/THIRD-PARTY-LICENSES.txt";
writeFileSync(out, parts.join("\n\n" + "-".repeat(78) + "\n\n") + "\n");
console.log(`licenses of ${parts.length} packages written to ${out}`);
