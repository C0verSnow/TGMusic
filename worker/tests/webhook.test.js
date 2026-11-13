import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import worker, { parseUpdate } from '../index.js';

function fixture() {
  const dir = mkdtempSync(join(tmpdir(), 'tgmusic-worker-'));
  const database = join(dir, 'db.sqlite');
  function query(sql, params = []) {
    const result = spawnSync('python3', ['worker/tests/sqlite_bridge.py', database], {
      input: JSON.stringify({ sql, params }), encoding: 'utf8',
    });
    assert.equal(result.status, 0, result.stderr);
    return JSON.parse(result.stdout);
  }
  const setup = spawnSync('python3', ['worker/tests/sqlite_bridge.py', database], {
    input: JSON.stringify({ script: readFileSync('migrations/0001_initial.sql', 'utf8') }), encoding: 'utf8',
  });
  assert.equal(setup.status, 0, setup.stderr);
  query("INSERT INTO installation(id,installation_id) VALUES(1,'test')");
  query("INSERT INTO roles(user_id,role) VALUES(1,'owner'),(2,'admin')");
  query("INSERT INTO targets(chat_id,type) VALUES(-100,'group'),(-200,'group')");
  query('INSERT INTO admin_targets(user_id,chat_id) VALUES(2,-100)');
  const env = { TELEGRAM_WEBHOOK_SECRET: 'secret', TELEGRAM_BOT_TOKEN: 'fake-token',
    TELEGRAM_BOT_USERNAME: 'testbot', GITHUB_REPOSITORY: 'owner/repo', GITHUB_REF: 'main',
    GITHUB_WORKFLOW_TRIGGER_TOKEN: 'fake-trigger',
    DB: { prepare(sql) { return { bind(...params) { return {
      async first() { return query(sql, params)[0] || null; },
      async all() { return { results: query(sql, params) }; },
      async run() { return { results: query(sql, params) }; },
    }; } }; } },
    PROFILES: { async head() { return {}; } },
  };
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, data: JSON.parse(options.body) });
    if (url.includes('api.github.com')) return new Response(null, { status: 204 });
    return Response.json({ ok: true, result: url.endsWith('getChatMember') ? { status: 'administrator' } : { message_id: 1 } });
  };
  let sequence = 0;
  async function send(text, userId = 1, chatId = userId, token = 'secret', updateId) {
    const pending = [];
    const request = new Request('https://test/webhook', { method: 'POST',
      headers: { 'X-Telegram-Bot-Api-Secret-Token': token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ update_id: updateId ?? ++sequence, message: { text,
        from: { id: userId, is_bot: false }, chat: { id: chatId, type: chatId < 0 ? 'supergroup' : 'private' } } }),
    });
    const response = await worker.fetch(request, env, { waitUntil(promise) { pending.push(promise); } });
    await Promise.all(pending);
    return response;
  }
  return { query, env, calls, send, cleanup() { globalThis.fetch = original; rmSync(dir, { recursive: true, force: true }); } };
}

test('webhook rejects missing/wrong secret before dispatch', async () => {
  const f = fixture();
  try {
    assert.equal((await f.send('/sync', 1, 1, 'wrong')).status, 403);
    assert.equal(f.calls.length, 0);
  } finally { f.cleanup(); }
});

test('guest has help only and joining a group never authorizes it', async () => {
  const f = fixture();
  try {
    await f.send('/help', 99);
    await f.send('/sync', 99);
    assert.equal(f.calls.filter(x => x.url.includes('github')).length, 0);
    assert.match(f.calls.at(-1).data.text, /权限不足/);
    await f.send('/sync', 2, -999);
    assert.equal(f.query('SELECT * FROM targets WHERE chat_id=-999').length, 0);
  } finally { f.cleanup(); }
});

test('owner dispatches once; duplicate update and rapid commands are limited', async () => {
  const f = fixture();
  try {
    await f.send('/sync', 1, 1, 'secret', 40);
    await f.send('/sync', 1, 1, 'secret', 40);
    await f.send('/sync', 1, 1, 'secret', 41);
    assert.equal(f.calls.filter(x => x.url.includes('github')).length, 1);
    assert.deepEqual(f.calls.find(x => x.url.includes('github')).data, { ref: 'main', inputs: { reply_chat_id: '1' } });
    assert.equal(f.query('SELECT * FROM audit_log').length, 2);
    const accepted = f.calls.find(x => x.data.text?.includes('已请求同步'));
    assert.doesNotMatch(accepted.data.text, /同步完成/);
    assert.match(accepted.data.text, /docs\/latest\.md/);
  } finally { f.cleanup(); }
});

test('admin only sees and controls assigned groups', async () => {
  const f = fixture();
  try {
    await f.send('/targets', 2);
    assert.match(f.calls.at(-1).data.text, /-100/);
    assert.doesNotMatch(f.calls.at(-1).data.text, /-200/);
    f.query('DELETE FROM command_limits');
    await f.send('/disable -200', 2);
    assert.equal(f.query('SELECT enabled FROM targets WHERE chat_id=-200')[0].enabled, 1);
    f.query('DELETE FROM command_limits');
    await f.send('/disable', 2, -100);
    assert.equal(f.query('SELECT enabled FROM targets WHERE chat_id=-100')[0].enabled, 0);
    await f.send('/sync', 2, -200);
    assert.equal(f.calls.filter(x => x.url.includes('github')).length, 0);
  } finally { f.cleanup(); }
});

test('owner adds groups for backfill and removal preserves history', async () => {
  const f = fixture();
  try {
    await f.send('/addtarget -300 audio');
    assert.equal(f.query('SELECT initial_mode FROM targets WHERE chat_id=-300')[0].initial_mode, 'all');
    f.query("INSERT INTO history(chat_id,video_id,title,artist,status) VALUES(-300,'abcdefghijk','Song','Artist','sent')");
    f.query('DELETE FROM command_limits');
    await f.send('/removetarget -300');
    assert.equal(f.query('SELECT removed FROM targets WHERE chat_id=-300')[0].removed, 1);
    assert.equal(f.query('SELECT * FROM history WHERE chat_id=-300').length, 1);
  } finally { f.cleanup(); }
});

test('ignores ordinary messages, malformed updates and bot messages', () => {
  assert.equal(parseUpdate({}), null);
  assert.equal(parseUpdate({ update_id: 1, message: { from: { id: 1 }, chat: { id: 1, type: 'private' }, text: 'hello' } }), null);
});

test('admin sync dispatch is limited to assigned targets', async () => {
  const f = fixture();
  try {
    await f.send('/sync', 2);
    const dispatched = f.calls.find(x => x.url.includes('github'));
    assert.deepEqual(dispatched.data, { ref: 'main', inputs: { reply_chat_id: '2', target_chat_ids: '[-100]' } });
  } finally { f.cleanup(); }
});


test('addressed sync in an authorized group dispatches only that group', async () => {
  const f = fixture();
  try {
    await f.send('/sync@testbot', 1, -100);
    assert.deepEqual(f.calls.find(x => x.url.includes('github')).data,
      { ref: 'main', inputs: { reply_chat_id: '-100', target_chat_ids: '[-100]' } });
    f.query('DELETE FROM command_limits');
    await f.send('/sync@anotherbot', 1, -100);
    assert.equal(f.calls.filter(x => x.url.includes('github')).length, 1);
  } finally { f.cleanup(); }
});
