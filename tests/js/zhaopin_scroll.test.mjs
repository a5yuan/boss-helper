import test from 'node:test';
import assert from 'node:assert/strict';
import { el, makeDocument } from './dom.mjs';
import { runProbe } from './run.mjs';

const PROBE = 'zhaopin_scroll.js';
const subs = (selector, scrollWindow = true) => ({
  "'__SELECTOR__'": JSON.stringify(selector),
  '__SCROLL_WINDOW__': String(scrollWindow),
});

test('正常：窗口滚到底，面板也滚到底', () => {
  const panel = el('div', { className: 'job-list-panel', scrollHeight: 5000 });
  const scrolls = [];
  const result = runProbe(PROBE, {
    state: {},
    document: makeDocument([panel]),
    subs: subs('.job-list-panel'),
    windowExtras: { scrollTo: (x, y) => scrolls.push([x, y]) },
  });
  assert.deepEqual(result, { ok: true });
  assert.deepEqual(scrolls, [[0, 1000]]);
  assert.equal(panel.scrollTop, 5000);
});

test('缺字段：面板不存在时仍返回 ok（只滚窗口）', () => {
  const scrolls = [];
  const result = runProbe(PROBE, {
    state: {},
    document: makeDocument(),
    subs: subs('.job-detail-panel'),
    windowExtras: { scrollTo: (x, y) => scrolls.push([x, y]) },
  });
  assert.deepEqual(result, { ok: true });
  assert.equal(scrolls.length, 1);
});

test('SCROLL_WINDOW=false 时只滚面板', () => {
  const panel = el('div', { className: 'job-detail-panel', scrollHeight: 320 });
  const scrolls = [];
  const result = runProbe(PROBE, {
    state: {},
    document: makeDocument([panel]),
    subs: subs('.job-detail-panel', false),
    windowExtras: { scrollTo: (x, y) => scrolls.push([x, y]) },
  });
  assert.deepEqual(result, { ok: true });
  assert.deepEqual(scrolls, []);
  assert.equal(panel.scrollTop, 320);
});

test('结构变了：window.scrollTo 不存在时返回 ok:false 而不是抛异常', () => {
  const result = runProbe(PROBE, {
    state: {},
    document: makeDocument([el('div', { className: 'job-list-panel' })]),
    subs: subs('.job-list-panel'),
  });
  assert.equal(result.ok, false);
  assert.match(result.reason, /scrollTo/);
});
