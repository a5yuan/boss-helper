import test from 'node:test';
import assert from 'node:assert/strict';
import { makeDocument } from './dom.mjs';
import { runProbe } from './run.mjs';
import { JOB_ID, cards, makeItem, otherItem } from './fixtures.mjs';

const PROBE = 'zhaopin_click.js';
const withId = id => ({ '__JOB_ID__': JSON.stringify(String(id)) });

test('正常：命中序号并把卡片滚进可视区', () => {
  const list = cards(3);
  const document = makeDocument(list);
  const result = runProbe(PROBE, {
    state: { positionList: [makeItem(), otherItem(), otherItem({ number: 'x' })] },
    document,
    subs: withId(JOB_ID),
  });
  assert.deepEqual(result, { index: 0, total: 3, scrolled: true });
  assert.equal(list[0].scrolledIntoView, 1);
  // lastScrollOptions 来自 vm 沙箱，跨 realm 的对象不能直接 deepEqual
  assert.equal(list[0].lastScrollOptions.block, 'center');
});

test('结构变了：state 有条目但卡片数量更少时，只报 index 不滚动', () => {
  const document = makeDocument(cards(2));
  const result = runProbe(PROBE, {
    state: { positionList: [otherItem(), otherItem({ number: 'b' }), otherItem({ number: 'c' }), makeItem()] },
    document,
    subs: withId(JOB_ID),
  });
  assert.equal(result.index, 3);
  assert.equal(result.total, 4);
  assert.equal(result.scrolled, false);
});

test('缺字段：岗位不在列表时返回 index -1', () => {
  const result = runProbe(PROBE, {
    state: { positionList: [makeItem()] },
    document: makeDocument(cards(1)),
    subs: withId('NOPE'),
  });
  assert.deepEqual(result, { index: -1, total: 1, scrolled: false });
});

test('结构变了：页面上没有卡片时不抛异常', () => {
  const result = runProbe(PROBE, {
    state: { positionList: [makeItem()] },
    document: makeDocument(),
    subs: withId(JOB_ID),
  });
  assert.deepEqual(result, { index: 0, total: 1, scrolled: false });
});
