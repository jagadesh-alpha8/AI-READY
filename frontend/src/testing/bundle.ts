/**
 * For `npm test` (Node's test runner) only: compile a .tsx component with esbuild (installed with Vite)
 * so a test can render it with react-dom/server. `stubs` replaces modules by import path ending -- e.g.
 * the API client or auth context -- with the given source, so nothing reaches the network.
 * Excluded from the app's type-check (tsconfig.json), as it uses node:* modules.
 */
import { mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const EXTERNAL = ['react', 'react/jsx-runtime', 'react-dom', 'react-dom/server', 'react-router-dom', 'lucide-react'];

export async function bundleComponent(entry: URL, stubs: Record<string, string> = {}) {
  const esbuild = await import('esbuild');
  // Inside the project, so the compiled file resolves react etc. from node_modules.
  const cache = fileURLToPath(new URL('../../node_modules/.cache/', import.meta.url));
  mkdirSync(cache, { recursive: true });
  const dir = mkdtempSync(join(cache, 'ui-test-'));
  const out = join(dir, 'bundle.mjs');
  await esbuild.build({
    entryPoints: [fileURLToPath(entry)],
    outfile: out, bundle: true, format: 'esm', platform: 'node', jsx: 'automatic', logLevel: 'silent',
    external: EXTERNAL,
    plugins: [{
      name: 'stubs',
      setup(build) {
        build.onResolve({ filter: /.*/ }, (args) => {
          const key = Object.keys(stubs).find((k) => args.path === k || args.path.endsWith(k));
          return key ? { path: key, namespace: 'stub' } : undefined;
        });
        build.onLoad({ filter: /.*/, namespace: 'stub' }, (args) => ({
          contents: stubs[args.path], loader: 'tsx', resolveDir: dir,
        }));
      },
    }],
  });
  const mod = await import(pathToFileURL(out).href);
  return { mod, cleanup: () => rmSync(dir, { recursive: true, force: true }) };
}
