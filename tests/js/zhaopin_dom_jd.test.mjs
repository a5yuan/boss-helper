import test from 'node:test';
import assert from 'node:assert/strict';
import { el, makeDocument } from './dom.mjs';
import { runProbe } from './run.mjs';

const PROBE = 'zhaopin_dom_jd.js';

test('正常：返回详情面板正文', () => {
  const document = makeDocument([
    el('div', {
      className: 'job-detail-modules__detail',
      text: '负责服务端开发与维护。',
    }),
  ]);
  const result = runProbe(PROBE, { state: {}, document });
  assert.deepEqual(result, { text: '负责服务端开发与维护。' });
});

test('缺字段：没有详情节点时返回空串', () => {
  const result = runProbe(PROBE, { state: {}, document: makeDocument() });
  assert.deepEqual(result, { text: '' });
});

test('结构变了：选择器被换掉时返回空串，不拿别的文本冒充 JD', () => {
  const document = makeDocument([
    el('div', { className: 'new-detail-modules__body', text: '新版正文' }),
  ]);
  const result = runProbe(PROBE, { state: {}, document });
  assert.deepEqual(result, { text: '' });
});

test('异常：查询抛错时返回空串和 error', () => {
  const document = {
    body: null,
    querySelectorAll() { throw new Error('boom'); },
    querySelector() { throw new Error('boom'); },
  };
  const result = runProbe(PROBE, { state: {}, document });
  assert.equal(result.text, '');
  assert.match(result.error, /boom/);
});
