import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { makeDocument } from './dom.mjs';
import { runProbe, JS_DIR } from './run.mjs';

const PROBE = 'zhaopin_login.js';

test('正常：游客可读页面报 in / guest_session', () => {
  const result = runProbe(PROBE, { state: { user: [] }, document: makeDocument() });
  assert.deepEqual(result, { state: 'in', source: 'guest_session' });
});

test('正常：user 非空报 in / state_user', () => {
  const result = runProbe(PROBE, { state: { user: { id: 1 } }, document: makeDocument() });
  assert.deepEqual(result, { state: 'in', source: 'state_user' });
});

test('缺字段：没有 user 字段仍按游客处理', () => {
  const result = runProbe(PROBE, { state: {}, document: makeDocument() });
  assert.deepEqual(result, { state: 'in', source: 'guest_session' });
});

test('登录入口页报 login / login_url', () => {
  const result = runProbe(PROBE, {
    state: {},
    document: makeDocument(),
    href: 'https://passport.zhaopin.com/login',
  });
  assert.deepEqual(result, { state: 'login', source: 'login_url' });
});

test('结构变了：非智联页面报 unknown / not_zhaopin', () => {
  const result = runProbe(PROBE, {
    state: {},
    document: makeDocument(),
    href: 'https://www.zhipin.com/web/geek/job',
  });
  assert.deepEqual(result, { state: 'unknown', source: 'not_zhaopin' });
});

test('异常：location 读不到时返回 unknown / error', () => {
  const location = {};
  Object.defineProperty(location, 'href', {
    get() { throw new Error('boom'); },
  });
  const code = fs.readFileSync(path.join(JS_DIR, PROBE), 'utf8');
  const raw = vm.runInNewContext(code, {
    window: { __INITIAL_STATE__: {} },
    document: makeDocument(),
    location,
  });
  assert.deepEqual(JSON.parse(raw), { state: 'unknown', source: 'error' });
});
