import { test } from 'node:test';
import assert from 'node:assert/strict';

import { versionedStore, type Answer } from './versioned.ts';

/** A stand-in server: answers 304 when the client holds the current version. */
function server() {
  let current = { version: 'v1', score: 18 };
  const seen: (string | null)[] = [];
  const fetcher = async (_key: string, held: string | null): Promise<Answer<unknown>> => {
    seen.push(held);
    await new Promise((r) => setTimeout(r, 1));
    return held === current.version ? { status: 304, data: '' } : { status: 200, data: { ...current } };
  };
  return { fetcher, seen, change: (next: { version: string; score: number }) => { current = next; } };
}

test('a kept copy is reused only after the server confirms its version', async () => {
  const s = server();
  const store = versionedStore(s.fetcher);
  const first = await store.get<{ version: string; score: number }>('/runs/a');
  const second = await store.get<{ version: string; score: number }>('/runs/a');
  assert.deepEqual(s.seen, [null, 'v1']);           // the second screen still asked
  assert.equal(second.data, first.data);             // and got the same copy back
  s.change({ version: 'v2', score: 26 });            // e.g. explanations written after completion
  const third = await store.get<{ version: string; score: number }>('/runs/a');
  assert.equal(third.data.score, 26);                // never the stale copy
  assert.deepEqual(s.seen, [null, 'v1', 'v1']);
  assert.equal((await store.get<{ version: string; score: number }>('/runs/a')).data.score, 26);
  assert.deepEqual(s.seen.at(-1), 'v2');
});

test('requests made at the same moment share one', async () => {
  const s = server();
  const store = versionedStore(s.fetcher);
  const [a, b, c] = await Promise.all([store.get('/runs/a'), store.get('/runs/a'), store.get('/runs/b')]);
  assert.equal(s.seen.length, 2);
  assert.equal(a.data, b.data);
  assert.notEqual(a.data, c.data);
});

test('an answer without a version is not kept, and old runs are let go', async () => {
  let n = 0;
  const store = versionedStore(async () => ({ status: 200, data: { n: ++n } }), 2);
  await store.get('/runs/a');
  assert.equal(store.size(), 0);
  const versioned = versionedStore(async (key) => ({ status: 200, data: { version: key } }), 2);
  for (const key of ['/a', '/b', '/c']) await versioned.get(key);
  assert.equal(versioned.size(), 2);
  versioned.clear();
  assert.equal(versioned.size(), 0);
});

test('a failed request is not kept and does not block the next', async () => {
  let fail = true;
  const store = versionedStore(async () => {
    if (fail) throw new Error('offline');
    return { status: 200, data: { version: 'v1' } };
  });
  await assert.rejects(store.get('/runs/a'));
  fail = false;
  assert.equal((await store.get<{ version: string }>('/runs/a')).data.version, 'v1');
});

test('304 without a kept copy is an error, not an empty run', async () => {
  const store = versionedStore(async () => ({ status: 304, data: '' }));
  await assert.rejects(store.get('/runs/a'));
});
