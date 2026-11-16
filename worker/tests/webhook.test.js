import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import worker, { parseUpdate } from '../index.js';

function fixture({ memberStatus = 'administrator', dispatchStatus = 204 } = {}) {
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
    input: JSON.stringify({ script: readdirSync('migrations').filter(name => name.endsWith('.sql')).sort()
      .map(name => readFileSync(join('migrations', name), 'utf8')).join('\n') }), encoding: 'utf8',
  });
  assert.equal(setup.status, 0, setup.stderr);
  query("INSERT INTO installation(id,installation_id) VALUES(1,'test')");
  query("INSERT INTO roles(user_id,role) VALUES(1,'owner'),(2,'admin')");
  query("INSERT INTO targets(chat_id,type) VALUES(-100,'group'),(-200,'group')");
  query('INSERT INTO admin_targets(user_id,chat_id) VALUES(2,-100)');
  const env = { TELEGRAM_WEBHOOK_SECRET: 'secret', TELEGRAM_BOT_TOKEN: 'fake-token',
    TELEGRAM_BOT_USERNAME: 'C0verSnow_TGMusic_bot', GITHUB_REPOSITORY: 'owner/repo', GITHUB_REF: 'main',
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
    if (url.includes('api.github.com')) return new Response(null, { status: dispatchStatus });
    return Response.json({ ok: true, result: url.endsWith('getChatMember') ? { status: memberStatus } : { message_id: 1 } });
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
    await f.send('/sync@C0verSnow_TGMusic_bot', 1, -100);
    assert.deepEqual(f.calls.find(x => x.url.includes('github')).data,
      { ref: 'main', inputs: { reply_chat_id: '-100', target_chat_ids: '[-100]' } });
    f.query('DELETE FROM command_limits');
    await f.send('/sync@anotherbot', 1, -100);
    assert.equal(f.calls.filter(x => x.url.includes('github')).length, 1);
  } finally { f.cleanup(); }
});

test('owner authorizes a new group in place, then sync stays in that group', async () => {
  const f = fixture();
  try {
    await f.send('/addtarget@C0verSnow_TGMusic_bot', 1, -300);
    assert.deepEqual(f.query('SELECT chat_id,type,send_mode,initial_mode FROM targets WHERE chat_id=-300'),
      [{ chat_id: -300, type: 'group', send_mode: 'audio', initial_mode: 'all' }]);
    assert.match(f.calls.at(-1).data.text, /-300（audio）/);
    assert.equal(f.calls.filter(x => x.url.includes('github')).length, 0);
    f.query('DELETE FROM command_limits');
    await f.send('/sync@C0verSnow_TGMusic_bot', 1, -300);
    assert.deepEqual(f.calls.find(x => x.url.includes('github')).data,
      { ref: 'main', inputs: { reply_chat_id: '-300', target_chat_ids: '[-300]' } });
  } finally { f.cleanup(); }
});

test('group shorthand accepts link and reauthorization preserves sending history', async () => {
  const f = fixture();
  try {
    f.query("UPDATE targets SET removed=1,enabled=0,initialized=1 WHERE chat_id=-100");
    f.query("INSERT INTO history(chat_id,video_id,title,artist,status) VALUES(-100,'abcdefghijk','Song','Artist','sent')");
    await f.send('/addtarget link', 1, -100);
    assert.deepEqual(f.query('SELECT removed,enabled,initialized,send_mode FROM targets WHERE chat_id=-100'),
      [{ removed: 0, enabled: 1, initialized: 1, send_mode: 'link' }]);
    assert.equal(f.query("SELECT * FROM history WHERE chat_id=-100 AND status='sent'").length, 1);
    assert.equal(f.query('SELECT send_mode FROM targets WHERE chat_id=-200')[0].send_mode, 'audio');
  } finally { f.cleanup(); }
});

test('group shorthand never lets guests or system admins authorize groups', async () => {
  const f = fixture();
  try {
    for (const user of [99, 2]) {
      await f.send('/addtarget', user, -300);
      assert.match(f.calls.at(-1).data.text, /权限不足/);
    }
    assert.equal(f.query('SELECT * FROM targets WHERE chat_id=-300').length, 0);
  } finally { f.cleanup(); }
});

test('owner must also be a Telegram group admin to authorize in place', async () => {
  const f = fixture({ memberStatus: 'member' });
  try {
    await f.send('/addtarget', 1, -300);
    assert.match(f.calls.at(-1).data.text, /权限不足/);
    assert.equal(f.query('SELECT * FROM targets WHERE chat_id=-300').length, 0);
  } finally { f.cleanup(); }
});

test('private shorthand and malformed target arguments never change targets', async () => {
  const f = fixture();
  try {
    for (const [text, chat] of [['/addtarget', 1], ['/addtarget link', 1], ['/addtarget video', -300],
      ['/addtarget audio extra', -300], ['/addtarget -400 audio extra', 1]]) {
      f.query('DELETE FROM command_limits');
      await f.send(text, 1, chat);
      assert.match(f.calls.at(-1).data.text, /用法/);
    }
    assert.equal(f.query('SELECT * FROM targets').length, 2);
    await f.send('/addtarget@C0verSnow_TGMusic_Test_bot', 1, -300);
    assert.equal(f.query('SELECT * FROM targets WHERE chat_id=-300').length, 0);
  } finally { f.cleanup(); }
});


test('id works before target authorization, while targetlist keeps role scope', async () => {
  const f = fixture();
  try {
    await f.send('/id@C0verSnow_TGMusic_bot', 99, -999);
    assert.equal(f.calls.at(-1)?.data.text, '当前聊天 ID：-999');
    await f.send('/id', 99);
    assert.equal(f.calls.at(-1).data.text, '当前聊天 ID：99');
    f.query('UPDATE targets SET enabled=0 WHERE chat_id=-100');
    f.query("INSERT INTO targets(chat_id,type,removed) VALUES(-300,'group',1)");
    await f.send('/targetlist', 2);
    assert.match(f.calls.at(-1).data.text, /-100.*暂停/);
    assert.doesNotMatch(f.calls.at(-1).data.text, /-200|-300/);
    await f.send('/targetlist', 1);
    assert.match(f.calls.at(-1).data.text, /-100/);
    assert.match(f.calls.at(-1).data.text, /-200/);
    assert.doesNotMatch(f.calls.at(-1).data.text, /-300/);
    await f.send('/targetlist', 99);
    assert.match(f.calls.at(-1).data.text, /权限不足/);
    assert.equal(f.calls.filter(x => x.url.includes('github')).length, 0);
  } finally { f.cleanup(); }
});

test('owner can persist an interval, pause and resume; invalid values never change settings', async () => {
  const f = fixture();
  try {
    await f.send('/autosync');
    assert.match(f.calls.at(-1)?.data.text || '', /每 6 小时/);
    for (const value of ['0', '-1', '1.5', '169', '3 extra', 'on extra']) {
      f.query('DELETE FROM command_limits');
      await f.send(`/autosync ${value}`);
      assert.match(f.calls.at(-1).data.text, /用法/);
      assert.equal(f.query('SELECT interval_hours FROM sync_schedule')[0].interval_hours, 6);
    }
    f.query('DELETE FROM command_limits');
    await f.send('/autosync 3');
    const state = f.query('SELECT * FROM sync_schedule')[0];
    assert.equal(state.interval_hours, 3);
    assert.equal(state.enabled, 1);
    assert.ok(state.next_run >= Math.floor(Date.now() / 1000) + 3 * 3600 - 2);
    assert.match(f.calls.at(-1).data.text, /每 3 小时/);
    f.query('DELETE FROM command_limits');
    await f.send('/autosync off');
    assert.equal(f.query('SELECT enabled FROM sync_schedule')[0].enabled, 0);
    assert.match(f.calls.at(-1).data.text, /暂停/);
    f.query('DELETE FROM command_limits');
    await f.send('/autosync on');
    assert.equal(f.query('SELECT enabled FROM sync_schedule')[0].enabled, 1);
    assert.equal(f.query('SELECT interval_hours FROM sync_schedule')[0].interval_hours, 3);
    f.query('DELETE FROM command_limits');
    await f.send('/status');
    assert.match(f.calls.at(-1).data.text, /每 3 小时/);
    assert.match(f.calls.at(-1).data.text, /上次成功/);
    await f.send('/autosync 12', 2);
    assert.match(f.calls.at(-1).data.text, /权限不足/);
    await f.send('/autosync 12', 99);
    assert.equal(f.query('SELECT interval_hours FROM sync_schedule')[0].interval_hours, 3);
    assert.equal(f.calls.filter(x => x.url.includes('github')).length, 0);
  } finally { f.cleanup(); }
});

test('scheduled trigger dispatches all targets every six hours by default, not every tick', async () => {
  const f = fixture();
  try {
    await worker.scheduled({ scheduledTime: 100000000 }, f.env);
    assert.deepEqual(f.calls, [{ url: 'https://api.github.com/repos/owner/repo/actions/workflows/sync.yml/dispatches',
      data: { ref: 'main', inputs: {} } }]);
    assert.deepEqual(f.query('SELECT last_dispatch,next_run FROM sync_schedule'),
      [{ last_dispatch: 100000, next_run: 121600 }]);
    await worker.scheduled({ scheduledTime: 100300000 }, f.env);
    assert.equal(f.calls.length, 1);
    await worker.scheduled({ scheduledTime: 121600000 }, f.env);
    assert.equal(f.calls.length, 2);
    assert.equal(f.query('SELECT next_run FROM sync_schedule')[0].next_run, 143200);
  } finally { f.cleanup(); }
});

test('scheduled trigger honors stored interval and pause, skips uninitialized or inactive installations', async () => {
  const f = fixture();
  try {
    f.query('UPDATE sync_schedule SET enabled=0,interval_hours=12');
    await worker.scheduled({ scheduledTime: 100000000 }, f.env);
    assert.equal(f.calls.length, 0);
    f.query('UPDATE sync_schedule SET enabled=1');
    f.query('UPDATE installation SET lease_until=100100');
    await worker.scheduled({ scheduledTime: 100000000 }, f.env);
    assert.equal(f.calls.length, 0);
    f.query('UPDATE installation SET lease_until=0');
    f.query('UPDATE targets SET enabled=0');
    await worker.scheduled({ scheduledTime: 100000000 }, f.env);
    assert.equal(f.calls.length, 0);
    f.query('UPDATE targets SET enabled=1');
    await worker.scheduled({ scheduledTime: 100000000 }, f.env);
    assert.equal(f.query('SELECT next_run FROM sync_schedule')[0].next_run, 143200);
    f.query('DELETE FROM installation');
    await worker.scheduled({ scheduledTime: 143200000 }, f.env);
    assert.equal(f.calls.length, 1);
  } finally { f.cleanup(); }
});

test('rejected scheduled dispatch is retried at the next tick without advancing six hours', async () => {
  const f = fixture({ dispatchStatus: 403 });
  try {
    await assert.rejects(worker.scheduled({ scheduledTime: 100000000 }, f.env), /GitHub dispatch failed/);
    assert.deepEqual(f.query('SELECT last_dispatch,next_run FROM sync_schedule'), [{ last_dispatch: 0, next_run: 0 }]);
    await assert.rejects(worker.scheduled({ scheduledTime: 100300000 }, f.env), /GitHub dispatch failed/);
    assert.equal(f.calls.length, 2);
  } finally { f.cleanup(); }
});

test('manual sync does not move the automatic due time, and still works while paused', async () => {
  const f = fixture();
  try {
    f.query('UPDATE sync_schedule SET enabled=0,next_run=123456');
    await f.send('/sync');
    assert.equal(f.calls.filter(x => x.url.includes('github')).length, 1);
    assert.deepEqual(f.query('SELECT enabled,next_run FROM sync_schedule'), [{ enabled: 0, next_run: 123456 }]);
    await f.send('/help', 99);
    for (const command of ['/autosync', '/targetlist', '/id']) assert.ok(f.calls.at(-1).data.text.includes(command));
  } finally { f.cleanup(); }
});
