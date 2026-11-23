import test from 'node:test';
import assert from 'node:assert/strict';
import { makeDocument } from './dom.mjs';
import { runProbe } from './run.mjs';
import { JOB_ID, makeItem, otherItem } from './fixtures.mjs';

const PROBE = 'zhaopin_item.js';
const withId = id => ({ '__JOB_ID__': JSON.stringify(String(id)) });

test('正常：按 number 命中', () => {
  const result = runProbe(PROBE, {
    state: { positionList: [otherItem(), makeItem()] },
    document: makeDocument(),
    subs: withId(JOB_ID),
  });
  assert.equal(result.number, JOB_ID);
  assert.equal(result.companyName, '北京捷科智诚科技有限公司上海分公司');
});

test('正常：number 不中时按 jobId 兜底', () => {
  const result = runProbe(PROBE, {
    state: { positionList: [makeItem()] },
    document: makeDocument(),
    subs: withId('40911854305'),
  });
  assert.equal(result.number, JOB_ID);
});

test('缺字段：找不到岗位返回 null', () => {
  const result = runProbe(PROBE, {
    state: { positionList: [makeItem()] },
    document: makeDocument(),
    subs: withId('NOPE'),
  });
  assert.equal(result, null);
});

test('结构变了：positionList 缺失返回 null', () => {
  const result = runProbe(PROBE, {
    state: {},
    document: makeDocument(),
    subs: withId(JOB_ID),
  });
  assert.equal(result, null);
});
