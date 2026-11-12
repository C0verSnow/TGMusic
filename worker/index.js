const PUBLIC_HELP = '/start /help\n白名单用户：/status /sync /targets /enable /disable\nOwner：/addtarget <chat_id> [audio|link] /removetarget <chat_id> /authstatus /health';
const COMMANDS = new Set(['status', 'sync', 'targets', 'addtarget', 'removetarget', 'enable', 'disable', 'authstatus', 'health']);
const OWNER_ONLY = new Set(['addtarget', 'removetarget', 'authstatus', 'health']);

export default {
  async fetch(request, env, ctx) {
    if (new URL(request.url).pathname !== '/webhook' || request.method !== 'POST') {
      return new Response('Not found', { status: 404 });
    }
    if (!env.TELEGRAM_WEBHOOK_SECRET || request.headers.get('X-Telegram-Bot-Api-Secret-Token') !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response('Forbidden', { status: 403 });
    }
    let update;
    try {
      update = await request.json();
    } catch {
      return new Response('Invalid JSON', { status: 400 });
    }
    const input = parseUpdate(update);
    if (!input) return new Response('OK');
    ctx.waitUntil(processUpdate(input, env).catch(() => console.error('Webhook processing failed; details suppressed')));
    return new Response('OK');
  },
};

export function parseUpdate(update) {
  const message = update?.message;
  if (!Number.isSafeInteger(update?.update_id) || !message || message.from?.is_bot ||
      !Number.isSafeInteger(message.from?.id) || !Number.isSafeInteger(message.chat?.id) ||
      typeof message.text !== 'string' || !['private', 'group', 'supergroup'].includes(message.chat.type)) return null;
  const match = message.text.match(/^\/([a-z]+)(?:@([A-Za-z0-9_]+))?(?:\s+(.*))?$/s);
  if (!match) return null;
  if (message.chat.type === 'private' && message.chat.id !== message.from.id) return null;
  return { updateId: update.update_id, userId: message.from.id, chatId: message.chat.id,
    chatType: message.chat.type, command: match[1], addressedBot: match[2], args: (match[3] || '').trim().split(/\s+/).filter(Boolean) };
}

async function processUpdate(input, env) {
  if (input.addressedBot && input.addressedBot.toLowerCase() !== env.TELEGRAM_BOT_USERNAME?.toLowerCase()) return;
  const claimed = await env.DB.prepare('INSERT OR IGNORE INTO webhook_updates(update_id,processed_at) VALUES(?,?) RETURNING update_id')
    .bind(input.updateId, now()).first();
  if (!claimed) return;
  if (input.command === 'help' || input.command === 'start') {
    await reply(env, input.chatId, PUBLIC_HELP);
    return;
  }
  if (!COMMANDS.has(input.command)) return;
  const allowed = await authorize(input, env);
  await env.DB.prepare('INSERT INTO audit_log(user_id,chat_id,command,outcome,created_at) VALUES(?,?,?,?,?)')
    .bind(input.userId, input.chatId, input.command, allowed ? 'allowed' : 'denied', now()).run();
  if (!allowed) {
    await reply(env, input.chatId, '权限不足或调用太频繁。');
    return;
  }
  try {
    await execute(input, env, allowed);
  } catch {
    await reply(env, input.chatId, '操作失败，请稍后重试；已有数据已保留。');
  }
}

export async function authorize(input, env) {
  const role = await env.DB.prepare('SELECT role FROM roles WHERE user_id=?').bind(input.userId).first();
  if (!role || (OWNER_ONLY.has(input.command) && role.role !== 'owner')) return null;
  if (input.chatType !== 'private') {
    const target = await env.DB.prepare('SELECT chat_id FROM targets WHERE chat_id=? AND removed=0 AND type=\'group\'')
      .bind(input.chatId).first();
    if (!target && !(input.command === 'addtarget' && role.role === 'owner')) return null;
    if (!(await isGroupAdmin(env, input.chatId, input.userId))) return null;
    if (role.role === 'admin' && !(await assigned(env, input.userId, input.chatId))) return null;
  } else if (role.role === 'admin') {
    const scope = await env.DB.prepare('SELECT chat_id FROM admin_targets WHERE user_id=? LIMIT 1').bind(input.userId).first();
    if (!scope) return null;
  }
  const rate = await env.DB.prepare('INSERT INTO command_limits(user_id,chat_id,last_called) VALUES(?,?,?) '
    + 'ON CONFLICT(user_id,chat_id) DO UPDATE SET last_called=excluded.last_called WHERE command_limits.last_called<=? RETURNING user_id')
    .bind(input.userId, input.chatId, now(), now() - 10).first();
  return rate ? role.role : null;
}

async function execute(input, env, role) {
  const { command, chatId, args, userId } = input;
  if (command === 'sync') {
    await dispatch(env);
    await reply(env, chatId, '已请求同步，GitHub Actions 将执行任务。');
  } else if (command === 'targets' || command === 'status') {
    let query = 'SELECT t.chat_id,t.type,t.enabled,t.send_mode,t.initialized FROM targets t WHERE t.removed=0';
    const params = [];
    if (role === 'admin') {
      query += ' AND EXISTS(SELECT 1 FROM admin_targets a WHERE a.user_id=? AND a.chat_id=t.chat_id)';
      params.push(userId);
    }
    const rows = await env.DB.prepare(query + ' ORDER BY t.chat_id').bind(...params).all();
    const lines = rows.results.map(t => `${t.chat_id} ${t.type} ${t.enabled ? '启用' : '暂停'} ${t.send_mode} ${t.initialized ? '已建基线' : '待初始化'}`);
    if (command === 'status') {
      const installation = await env.DB.prepare('SELECT last_success FROM installation WHERE id=1').first();
      lines.unshift(`上次成功：${installation?.last_success ? new Date(installation.last_success * 1000).toISOString() : '暂无'}`);
    }
    await reply(env, chatId, lines.join('\n') || '暂无目标。');
  } else if (command === 'addtarget') {
    const targetId = targetArgument(args[0]);
    const mode = args[1] || 'audio';
    if (!targetId || !['audio', 'link'].includes(mode)) {
      await reply(env, chatId, '用法：/addtarget <数字 chat_id> [audio|link]');
      return;
    }
    if (targetId < 0 && !(await isGroupAdmin(env, targetId, userId))) {
      await reply(env, chatId, '你还必须是该 Telegram 群组的管理员。');
      return;
    }
    await telegram(env, 'getChat', { chat_id: targetId });
    await env.DB.prepare('INSERT INTO targets(chat_id,type,send_mode) VALUES(?,?,?) '
      + 'ON CONFLICT(chat_id) DO UPDATE SET removed=0,enabled=1,send_mode=excluded.send_mode')
      .bind(targetId, targetId < 0 ? 'group' : 'user', mode).run();
    await reply(env, chatId, '目标已授权。新目标首次只建立基线。');
  } else if (command === 'removetarget') {
    const targetId = targetArgument(args[0]);
    if (!targetId) { await reply(env, chatId, '用法：/removetarget <数字 chat_id>'); return; }
    await env.DB.prepare('UPDATE targets SET removed=1,enabled=0 WHERE chat_id=?').bind(targetId).run();
    await reply(env, chatId, '目标已移除，历史保留。');
  } else if (command === 'enable' || command === 'disable') {
    const targetId = args[0] ? targetArgument(args[0]) : chatId;
    if (!targetId || (role === 'admin' && !(await assigned(env, userId, targetId)))) {
      await reply(env, chatId, '权限不足。'); return;
    }
    if (targetId < 0 && !(await isGroupAdmin(env, targetId, userId))) {
      await reply(env, chatId, '需要该群组管理员身份。'); return;
    }
    const changed = await env.DB.prepare('UPDATE targets SET enabled=? WHERE chat_id=? AND removed=0 RETURNING chat_id')
      .bind(command === 'enable' ? 1 : 0, targetId).first();
    await reply(env, chatId, changed ? '目标已更新。' : '请先由 Owner 授权该目标。');
  } else if (command === 'authstatus') {
    const state = await env.DB.prepare('SELECT auth_state FROM installation WHERE id=1').first();
    await reply(env, chatId, `最近登录检测：${state?.auth_state || 'UNKNOWN'}`);
  } else if (command === 'health') {
    const state = await env.DB.prepare('SELECT last_success,lease_until FROM installation WHERE id=1').first();
    const profile = await env.PROFILES.head(env.R2_PROFILE_OBJECT || 'auth/google-profile.tar.enc');
    await reply(env, chatId, `D1：${state ? '正常' : '未初始化'}\nR2 档案：${profile ? '存在' : '缺失'}\n任务：${state?.lease_until > now() ? '运行中' : '空闲'}`);
  }
}

async function assigned(env, userId, chatId) {
  return !!(await env.DB.prepare('SELECT chat_id FROM admin_targets WHERE user_id=? AND chat_id=?')
    .bind(userId, chatId).first());
}

async function isGroupAdmin(env, chatId, userId) {
  try {
    const member = await telegram(env, 'getChatMember', { chat_id: chatId, user_id: userId });
    return ['creator', 'administrator'].includes(member.status);
  } catch { return false; }
}

function targetArgument(value) {
  if (!/^-?\d+$/.test(value || '')) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) && id !== 0 ? id : null;
}

async function dispatch(env) {
  const response = await fetch(`https://api.github.com/repos/${env.GITHUB_REPOSITORY}/actions/workflows/sync.yml/dispatches`, {
    method: 'POST', headers: { Authorization: `Bearer ${env.GITHUB_WORKFLOW_TRIGGER_TOKEN}`,
      Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'TGMusic-Worker' },
    body: JSON.stringify({ ref: env.GITHUB_REF || 'main' }), signal: AbortSignal.timeout(10000),
  });
  if (response.status !== 204) throw new Error('GitHub dispatch failed');
}

async function telegram(env, method, data) {
  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    signal: AbortSignal.timeout(10000),
  });
  const result = await response.json();
  if (!result.ok) throw new Error('Telegram request rejected');
  return result.result;
}

async function reply(env, chatId, text) {
  await telegram(env, 'sendMessage', { chat_id: chatId, text: text.slice(0, 4000) });
}

function now() { return Math.floor(Date.now() / 1000); }
