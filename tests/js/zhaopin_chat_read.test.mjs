import test from 'node:test';
import assert from 'node:assert/strict';
import { el, makeDocument } from './dom.mjs';
import { runProbe } from './run.mjs';

const PROBE = 'zhaopin_chat_read.js';

function chat({ textarea, messages = [], sendText = '发送' } = {}) {
  const children = [];
  if (textarea) children.push(textarea);
  if (messages.length) {
    children.push(el('div', {
      className: 'message-list',
      children: messages.map(text => el('div', { className: 'message-item', text })),
    }));
  }
  if (sendText) {
    children.push(el('button', {
      text: sendText,
      rect: { left: 500, top: 600, width: 80, height: 30 },
    }));
  }
  return makeDocument(children);
}

test('正常：输入框、消息、发送按钮都读出来', () => {
  const document = chat({
    textarea: el('textarea', { value: '', rect: { left: 100, top: 500, width: 300, height: 60 } }),
    messages: ['你好', '在吗'],
  });
  const result = runProbe(PROBE, { state: {}, document });
  assert.equal(result.ok, true);
  assert.equal(result.input_ready, true);
  assert.equal(result.input_len, 0);
  assert.deepEqual(result.messages, ['你好', '在吗']);
  assert.deepEqual(result.send, { found: true, x: 540, y: 615 });
});

test('缺字段：没有输入框时 input_ready 为 false，长度 -1', () => {
  const result = runProbe(PROBE, { state: {}, document: makeDocument() });
  assert.equal(result.ok, true);
  assert.equal(result.input_ready, false);
  assert.equal(result.input_len, -1);
  assert.deepEqual(result.messages, []);
  assert.equal(result.send.found, false);
});

test('结构变了：输入框尺寸过小被当成不可见', () => {
  const document = chat({
    textarea: el('textarea', { value: '草稿', rect: { left: 0, top: 0, width: 10, height: 5 } }),
    sendText: '',
  });
  const result = runProbe(PROBE, { state: {}, document });
  assert.equal(result.input_ready, false);
});

test('消息取最内层：外层容器不会把整段记录当成一条', () => {
  const result = runProbe(PROBE, {
    state: {},
    document: chat({ messages: ['甲', '乙', '丙'] }),
  });
  assert.deepEqual(result.messages, ['甲', '乙', '丙']);
});

test('contenteditable：读 innerText 长度，不依赖 value', () => {
  const document = chat({
    textarea: el('div', {
      attrs: { contenteditable: 'true' },
      text: '草稿内容',
      rect: { left: 0, top: 0, width: 300, height: 60 },
    }),
  });
  const result = runProbe(PROBE, { state: {}, document });
  assert.equal(result.input_ready, true);
  assert.equal(result.input_len, 4);
});

test('有多个输入框时取最后一个可见的', () => {
  const document = makeDocument([
    el('textarea', { value: '旧的', rect: { left: 0, top: 0, width: 300, height: 60 } }),
    el('textarea', { value: '新的草稿', rect: { left: 0, top: 100, width: 300, height: 60 } }),
  ]);
  const result = runProbe(PROBE, { state: {}, document });
  assert.equal(result.input_len, 4);
});

test('发送按钮取最内层，外层壳子不算', () => {
  const shell = el('div', {
    text: '发送',
    rect: { left: 500, top: 600, width: 80, height: 30 },
    children: [el('span', { text: '发送', rect: { left: 510, top: 605, width: 60, height: 20 } })],
  });
  const document = makeDocument([
    el('textarea', { value: '', rect: { left: 0, top: 0, width: 300, height: 60 } }),
    shell,
  ]);
  const result = runProbe(PROBE, { state: {}, document });
  assert.deepEqual(result.send, { found: true, x: 540, y: 615 });
});

test('文案不是精确「发送」时不误认', () => {
  const document = chat({
    textarea: el('textarea', { value: '', rect: { left: 0, top: 0, width: 300, height: 60 } }),
    sendText: '发送消息',
  });
  const result = runProbe(PROBE, { state: {}, document });
  assert.equal(result.send.found, false);
});

test('异常：查询抛错时返回 ok:false 和 reason', () => {
  const document = {
    body: el('body'),
    querySelectorAll() { throw new Error('boom'); },
    querySelector() { throw new Error('boom'); },
  };
  const result = runProbe(PROBE, { state: {}, document });
  assert.equal(result.ok, false);
  assert.match(result.reason, /chat_read_error: Error: boom/);
});
