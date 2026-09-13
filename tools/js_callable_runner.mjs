import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

function fail(message, name = 'Error') {
  process.stdout.write(`${JSON.stringify({ ok: false, error: { name, message } })}\n`);
  process.exitCode = 3;
}

try {
  const [targetPath, exportName] = process.argv.slice(2);
  if (!targetPath || !exportName) throw new TypeError('target path and export name are required');
  const requestText = readFileSync(0, 'utf8');
  const request = JSON.parse(requestText);
  if (request?.schema !== 'axm.callable-invocation-request/v0.1') {
    throw new TypeError('unsupported callable invocation request schema');
  }
  if (!Array.isArray(request.args)) throw new TypeError('request.args must be an array');

  const source = await import(pathToFileURL(targetPath).href);
  const callable = source[exportName];
  if (typeof callable !== 'function') throw new TypeError(`declared export is not a function: ${exportName}`);
  const result = await callable(...request.args);
  process.stdout.write(`${JSON.stringify({ ok: true, result: result === undefined ? null : result })}\n`);
} catch (error) {
  fail(String(error?.message || error), String(error?.name || 'Error'));
}
