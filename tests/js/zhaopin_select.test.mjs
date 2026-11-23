import test from 'node:test';
import assert from 'node:assert/strict';
import { makeDocument } from './dom.mjs';
import { runProbe } from './run.mjs';
import { cards } from './fixtures.mjs';

const PROBE = 'zhaopin_select.js';
const at = index => ({ '__INDEX__': String(index) });

test('正常：返回卡片中心坐标并滚动', () => {
  const list = cards(3);
  const result = runProbe(PROBE, {
    state: {},
    document: makeDocument(list),
    subs: at(1),
  });
  assert.deepEqual(result, { ok: true, total: 3, x: 150, y: 140 });
  assert.equal(list[1].scrolledIntoView, 1);
});

test('缺字段：序号越界返回 card_not_found', () => {
  const result = runProbe(PROBE, {
    state: {},
    document: makeDocument(cards(3)),
    subs: at(9),
  });
  assert.equal(result.ok, false);
  assert.equal(result.reason, 'card_not_found');
  assert.equal(result.total, 3);
});

test('结构变了：一个卡片都没有时返回 card_not_found', () => {
  const result = runProbe(PROBE, { state: {}, document: makeDocument(), subs: at(0) });
  assert.equal(result.ok, false);
  assert.equal(result.reason, 'card_not_found');
  assert.equal(result.total, 0);
});

test('异常：查询抛错时返回 select_error', () => {
  const document = {
    body: null,
    querySelectorAll() { throw new Error('boom'); },
    querySelector() { throw new Error('boom'); },
  };
  const result = runProbe(PROBE, { state: {}, document, subs: at(0) });
  assert.equal(result.ok, false);
  assert.match(result.reason, /select_error: Error: boom/);
});
