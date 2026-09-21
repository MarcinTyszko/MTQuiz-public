// Kopiuje zależności przeglądarkowe do katalogu statycznego aplikacji,
// dzięki czemu wdrożenie działa w pełni offline (bez CDN).
import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const target = resolve(here, "../app/static/vendor");

const files = [
  ["node_modules/alpinejs/dist/cdn.min.js", "alpine.min.js"],
];

await mkdir(target, { recursive: true });
for (const [from, to] of files) {
  await copyFile(resolve(here, from), resolve(target, to));
  console.log(`vendor: ${to}`);
}
