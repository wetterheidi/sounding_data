// Baut dist/ für den Deploy (nur das Web-Frontend):
// - sounding_viewer.html → dist/index.html
// - admin.html, favicon.svg, leaflet/
// - om/ (öffentliche Variante ohne Login)
//
// Python-Pipeline, locations.json und Daten gehören NICHT dazu; die liegen
// auf dem Server unter /apps/TLogPViewer (Git-Klon, per git pull).
//
// Aufruf: npm run build

import { rmSync, mkdirSync, copyFileSync, cpSync } from 'node:fs';
import { join, dirname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const dist = join(root, 'dist');

const files = [
  ['sounding_viewer.html', 'index.html'],
  ['admin.html', 'admin.html'],
  ['favicon.svg', 'favicon.svg'],
];
const dirs = ['leaflet', 'om'];

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist);

for (const [src, dest] of files) {
  copyFileSync(join(root, src), join(dist, dest));
  console.log(`==> dist/${dest} ← ${src}`);
}
for (const dir of dirs) {
  cpSync(join(root, dir), join(dist, dir), {
    recursive: true,
    filter: (src) => basename(src) !== '.DS_Store',
  });
  console.log(`==> dist/${dir}/`);
}
