import en from "../src/lib/messages/en.json" with { type: "json" };
import vi from "../src/lib/messages/vi.json" with { type: "json" };
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

function leaves(value, prefix = "") {
  if (typeof value === "string") return [[prefix, value]];
  return Object.entries(value).flatMap(([key, child]) =>
    leaves(child, prefix ? `${prefix}.${key}` : key),
  );
}

const english = new Map(leaves(en));
const vietnamese = new Map(leaves(vi));
const englishKeys = [...english.keys()].sort();
const vietnameseKeys = [...vietnamese.keys()].sort();
if (JSON.stringify(englishKeys) !== JSON.stringify(vietnameseKeys)) {
  throw new Error(
    `Translation key mismatch. en=${englishKeys.join(",")} vi=${vietnameseKeys.join(",")}`,
  );
}

function parameters(value) {
  return [...value.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
}

for (const key of englishKeys) {
  if (
    JSON.stringify(parameters(english.get(key))) !==
    JSON.stringify(parameters(vietnamese.get(key)))
  ) {
    throw new Error(`Translation parameter mismatch for ${key}`);
  }
}

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const sourceDirectory = join(scriptDirectory, "..", "src");
const phase3Roots = [
  "app/(authenticated)",
  "features/app-shell",
  "features/work-in-office",
].map((part) => join(sourceDirectory, part));
const literalAttributeAllowlist = new Set([
  "className",
  "href",
  "key",
  "method",
  "role",
  "scope",
  "type",
  "value",
]);
const userFacingAttributeNames = new Set([
  "aria-label",
  "placeholder",
  "title",
]);
const allowedCopy = new Set(["YAWN"]);

function filesIn(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) return filesIn(path);
    if (!/\.(tsx|ts)$/.test(path)) return [];
    if (/\.(test|spec)\./.test(path)) return [];
    return [path];
  });
}

function lineNumber(source, index) {
  return source.slice(0, index).split("\n").length;
}

function attributeBefore(source, index) {
  const prefix = source.slice(Math.max(0, index - 80), index);
  return prefix.match(/([A-Za-z-]+)\s*=\s*\{?\s*$/)?.[1] ?? null;
}

function shouldCheckStringLiteral(source, index, value) {
  if (value === "use client") return false;
  if (!/[A-Za-z]/.test(value)) return false;
  if (/[\n\r]/.test(value)) return false;
  if (/[{}[\]();<>=$]/.test(value)) return false;
  const prefix = source.slice(Math.max(0, index - 40), index);
  if (/\bfrom\s*$/.test(prefix) || /\bimport\s*\(?\s*$/.test(prefix))
    return false;
  if (/^\.{1,2}\//.test(value)) return false;
  const attribute = attributeBefore(source, index);
  if (attribute && literalAttributeAllowlist.has(attribute)) return false;
  if (attribute && userFacingAttributeNames.has(attribute)) return true;
  return /\s/.test(value);
}

function shouldCheckJsxText(value) {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (!normalized || !/[A-Za-z]/.test(normalized)) return false;
  if (/[{}[\]();<>=$?]/.test(normalized)) return false;
  if (/\b(const|let|return|role|useState|new Date|void)\b/.test(normalized))
    return false;
  return true;
}

const findings = [];
for (const file of phase3Roots.flatMap(filesIn)) {
  const source = readFileSync(file, "utf8");
  for (const match of source.matchAll(/(["'`])((?:\\.|(?!\1)[\s\S])*?)\1/g)) {
    const value = match[2].trim();
    if (allowedCopy.has(value)) continue;
    if (!shouldCheckStringLiteral(source, match.index, value)) continue;
    findings.push(
      `${relative(sourceDirectory, file)}:${lineNumber(source, match.index)} "${value}"`,
    );
  }
  for (const match of source.matchAll(/>([^<>{}]*[A-Za-z][^<>{}]*)</g)) {
    const value = match[1].replace(/\s+/g, " ").trim();
    if (allowedCopy.has(value)) continue;
    if (!shouldCheckJsxText(value)) continue;
    findings.push(
      `${relative(sourceDirectory, file)}:${lineNumber(source, match.index)} ${value}`,
    );
  }
}

if (findings.length) {
  throw new Error(
    `Hard-coded Phase 3 UI copy bypasses localization:\n${findings.join("\n")}`,
  );
}
