import test from 'node:test';
import assert from 'node:assert/strict';
import { makeDocument } from './dom.mjs';
import { runProbe } from './run.mjs';
import { makeItem, otherItem } from './fixtures.mjs';

const PROBE = 'zhaopin_list.js';

test('正常：返回 positionList 原样', () => {
  const items = [makeItem(), otherItem()];
  const result = runProbe(PROBE, { state: { positionList: items }, document: makeDocument() });
  assert.equal(result.length, 2);
  assert.equal(result[0].number, items[0].number);
  assert.equal(result[1].name, '前端开发工程师');
});

test('缺字段：没有 __INITIAL_STATE__ 时返回空数组', () => {
  const result = runProbe(PROBE, { state: {}, document: makeDocument() });
  assert.deepEqual(result, []);
});

test('结构变了：positionList 不是数组时返回空数组', () => {
  const result = runProbe(PROBE, {
    state: { positionList: { number: 'x' } },
    document: makeDocument(),
  });
  assert.deepEqual(result, []);
});

test('异常：读 state 抛错时返回 __error__ 而不是抛异常', () => {
  const state = {};
  Object.defineProperty(state, 'positionList', {
    get() { throw new Error('boom'); },
  });
  const result = runProbe(PROBE, { state, document: makeDocument() });
  assert.match(result.__error__, /boom/);
});
