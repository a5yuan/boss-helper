/* 测试数据构造器：只放探针真正读的字段，避免把真实页面结构抄一遍。 */
import { el } from './dom.mjs';

export const JOB_ID = 'CCL1405333700J40911854305';
export const OTHER_JOB_ID = 'CCL1405333700J40911800000';

export function makeItem(over = {}) {
  return {
    number: JOB_ID,
    jobId: 40911854305,
    name: '信贷测试（银行对公方向）',
    companyName: '北京捷科智诚科技有限公司上海分公司',
    salary60: '1-2万',
    cityDistrict: '滨江',
    education: '本科',
    workingExp: '3-5年',
    hasAppliedPosition: false,
    alreadyApply: false,
    applyType: '1',
    ...over,
  };
}

export function otherItem(over = {}) {
  return makeItem({
    number: OTHER_JOB_ID,
    jobId: 40911800000,
    name: '前端开发工程师',
    companyName: '另一家公司',
    ...over,
  });
}

export function cards(count) {
  return Array.from({ length: count }, (_, i) => el('div', {
    className: `job-card${i === 0 ? ' job-card--active' : ''}`,
    text: `岗位 ${i}`,
    rect: { left: 0, top: i * 100, width: 300, height: 80 },
  }));
}

export function detailPanel({ title, company, buttonText = '立即投递', disabled = false, withButton = true } = {}) {
  const children = [
    el('div', { className: 'job-detail-summary', children: [
      el('div', { className: 'job-detail-summary__title-text', text: title }),
      el('div', { className: 'job-detail-summary__company', text: company }),
    ] }),
  ];
  if (withButton) {
    children.push(el('button', {
      className: 'a-button job-detail-summary__apply a--bordered a--filled',
      text: buttonText,
      disabled,
      rect: { left: 1105, top: 245, width: 96, height: 36 },
    }));
  }
  return el('div', { className: 'job-detail-panel', children });
}
