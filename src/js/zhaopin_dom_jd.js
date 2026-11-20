/* zhaopin:dom-jd — 详情正文的 DOM 兜底。
   state 里的 jobDetailData.position.desc.description 通常完整；为空时
   才读详情面板渲染后的正文，避免把导航/按钮文字当成 JD。 */
(() => {
  try {
    const el = document.querySelector('.job-detail-modules__detail');
    return JSON.stringify({ text: el ? (el.innerText || '') : '' });
  } catch (e) {
    return JSON.stringify({ text: '', error: String(e) });
  }
})()
