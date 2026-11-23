import test from 'node:test';
import assert from 'node:assert/strict';
import { el, makeDocument } from './dom.mjs';
import { runProbe } from './run.mjs';

const PROBE = 'zhaopin_apply_modal.js';
const PHRASE = '已向对方发送简历和打招呼语';

function modal({ className = 'a-modal', width = 400, withPhrase = true, buttons = true } = {}) {
  const children = [];
  if (withPhrase) children.push(el('div', { text: PHRASE }));
  if (buttons) {
    children.push(el('div', {
      children: [
        el('button', { text: '留在此页', rect: { left: 100, top: 200, width: 80, height: 30 } }),
        el('button', { text: '继续沟通', rect: { left: 200, top: 200, width: 80, height: 30 } }),
      ],
    }));
  }
  return el('div', {
    className,
    width,
    rect: { left: 0, top: 0, width, height: 200 },
    children,
  });
}

test('正常：确认文案与两个按钮都读出来', () => {
  const result = runProbe(PROBE, { state: {}, document: makeDocument([modal()]) });
  assert.equal(result.confirmed, true);
  assert.equal(result.login, false);
  assert.ok(result.text.includes(PHRASE), `弹层文本应含确认文案: ${result.text}`);
  assert.deepEqual(result.continue, { found: true, text: '继续沟通', x: 240, y: 215 });
  assert.deepEqual(result.stay, { found: true, text: '留在此页', x: 140, y: 215 });
});

test('缺字段：没有弹窗时返回 confirmed:false，不误报登录', () => {
  const result = runProbe(PROBE, { state: {}, document: makeDocument() });
  assert.deepEqual(result, { confirmed: false, login: false, text: '' });
});

test('登录弹层：只有登录文案时报 login:true', () => {
  const document = makeDocument([el('div', { text: '请扫码登录后投递' })]);
  const result = runProbe(PROBE, { state: {}, document });
  assert.equal(result.confirmed, false);
  assert.equal(result.login, true);
});

test('结构变了：弹层 class 全换了，仍按确认文案兜底找到', () => {
  const document = makeDocument([modal({ className: 'new-layer' })]);
  const result = runProbe(PROBE, { state: {}, document });
  assert.equal(result.confirmed, true);
  assert.equal(result.continue.found, true);
});

test('不可见弹层不算确认', () => {
  const document = makeDocument([modal({ width: 0 })]);
  const result = runProbe(PROBE, { state: {}, document });
  assert.equal(result.confirmed, false);
  assert.equal(result.login, false);
  assert.equal(result.text, '');
});

test('按钮取最内层：外层壳子不返回，返回里面真正可点的节点', () => {
  const shell = el('div', {
    text: '继续沟通',
    rect: { left: 250, top: 300, width: 120, height: 40 },
    children: [el('span', { text: '继续沟通', rect: { left: 260, top: 305, width: 100, height: 30 } })],
  });
  const document = makeDocument([
    el('div', {
      className: 'a-modal',
      rect: { left: 0, top: 0, width: 400, height: 200 },
      children: [el('div', { text: PHRASE }), shell],
    }),
  ]);
  const result = runProbe(PROBE, { state: {}, document });
  assert.equal(result.confirmed, true);
  assert.deepEqual(result.continue, { found: true, text: '继续沟通', x: 310, y: 320 });
});

test('异常：查询抛错时返回 confirmed:false 和 reason', () => {
  const document = {
    body: el('body'),
    querySelectorAll() { throw new Error('boom'); },
    querySelector() { throw new Error('boom'); },
  };
  const result = runProbe(PROBE, { state: {}, document });
  assert.equal(result.confirmed, false);
  assert.match(result.reason, /modal_error: Error: boom/);
});
