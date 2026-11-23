import test from 'node:test';
import assert from 'node:assert/strict';
import { el, makeDocument } from './dom.mjs';
import { runProbe } from './run.mjs';
import { JOB_ID, OTHER_JOB_ID, detailPanel, makeItem, otherItem } from './fixtures.mjs';

const PROBE = 'zhaopin_apply_state.js';
const withId = id => ({ '__JOB_ID__': JSON.stringify(String(id)) });

function run({ item = makeItem(), selectedJobId = JOB_ID, user = { id: 1 }, panel, document } = {}) {
  const body = document || makeDocument([
    panel || detailPanel({ title: item.name, company: item.companyName }),
  ]);
  return runProbe(PROBE, {
    state: { positionList: [item], selectedJobId, user },
    document: body,
    subs: withId(JOB_ID),
  });
}

test('正常：DOM 与快照一致时读出全部字段和按钮坐标', () => {
  const result = run();
  assert.equal(result.ok, true);
  assert.equal(result.found, true);
  assert.equal(result.index, 0);
  assert.equal(result.number, JOB_ID);
  assert.equal(result.company, '北京捷科智诚科技有限公司上海分公司');
  assert.equal(result.title, '信贷测试（银行对公方向）');
  assert.equal(result.logged_in, true);
  assert.equal(result.selected, true);
  assert.deepEqual(result.button, {
    found: true, text: '立即投递', disabled: false,
    x: 1153, y: 263, w: 96, h: 36,
  });
});

test('回归：快照没更新（还指向别的岗位），但详情面板 DOM 已是目标岗位 → selected 必须为 true', () => {
  // 这就是 selectedJobId 是 SSR 快照、hydrate 后不回写导致的线上 bug。
  const result = run({ selectedJobId: OTHER_JOB_ID });
  assert.equal(result.selected, true);
  assert.equal(result.button.found, true);
});

test('安全：DOM 显示的是别的岗位、快照还停在目标岗位 → selected 必须为 false，且不给按钮坐标', () => {
  // 详情面板才是点击「立即投递」真正作用的岗位；快照这时是过期数据，不能覆盖 DOM。
  const result = run({
    selectedJobId: JOB_ID,
    panel: detailPanel({ title: '前端开发工程师', company: '另一家公司' }),
  });
  assert.equal(result.selected, false);
  assert.equal(result.button.found, false);
});

test('兜底：DOM 标题读不到时才用快照判断', () => {
  const result = run({
    selectedJobId: JOB_ID,
    panel: detailPanel({ title: '', company: '北京捷科智诚科技有限公司上海分公司' }),
  });
  assert.equal(result.selected, true);
  assert.equal(result.button.found, true);
});

test('结构变了：DOM 标题对但公司不在面板里 → 不判选中（无法确认是同一条）', () => {
  const result = run({
    selectedJobId: JOB_ID,
    panel: detailPanel({ title: '信贷测试（银行对公方向）', company: '' }),
  });
  assert.equal(result.selected, false);
});

test('缺字段：岗位不在列表返回 found:false 和 reason', () => {
  const result = runProbe(PROBE, {
    state: { positionList: [otherItem()], selectedJobId: OTHER_JOB_ID, user: {} },
    document: makeDocument(),
    subs: withId(JOB_ID),
  });
  assert.equal(result.ok, true);
  assert.equal(result.found, false);
  assert.equal(result.reason, 'job_not_in_list');
});

test('已投字段原样返回', () => {
  const result = run({
    item: makeItem({ hasAppliedPosition: true, alreadyApply: true, applyType: '2' }),
  });
  assert.equal(result.has_applied_position, true);
  assert.equal(result.already_apply, true);
  assert.equal(result.apply_type, '2');
});

test('游客：user 是空数组时 logged_in 为 false', () => {
  const result = run({ user: [] });
  assert.equal(result.logged_in, false);
});

test('结构变了：按钮选择器不存在时 selected 为 true 但 button.found 为 false', () => {
  const result = run({
    panel: detailPanel({
      title: '信贷测试（银行对公方向）',
      company: '北京捷科智诚科技有限公司上海分公司',
      withButton: false,
    }),
  });
  assert.equal(result.selected, true);
  assert.equal(result.button.found, false);
});

test('按钮 disabled 原样返回', () => {
  const result = run({
    panel: detailPanel({
      title: '信贷测试（银行对公方向）',
      company: '北京捷科智诚科技有限公司上海分公司',
      buttonText: '已投递',
      disabled: true,
    }),
  });
  assert.equal(result.button.found, true);
  assert.equal(result.button.disabled, true);
  assert.equal(result.button.text, '已投递');
});

test('异常：DOM 查询抛错时返回 ok:false 和 reason', () => {
  const document = {
    body: el('body'),
    querySelectorAll() { throw new Error('boom'); },
    querySelector() { throw new Error('boom'); },
  };
  const result = runProbe(PROBE, {
    state: { positionList: [makeItem()], selectedJobId: JOB_ID, user: { id: 1 } },
    document,
    subs: withId(JOB_ID),
  });
  assert.equal(result.ok, false);
  assert.match(result.reason, /state_error: Error: boom/);
});
