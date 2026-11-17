(() => {
    // 读详情页招聘者区块的活跃状态。BOSS 详情页结构：.job-boss-info
    // 里面是「姚女士 刚刚活跃 外企德科数字 · 招聘专员」这样一段文本。
    // 页面结构变化时返回 {ok:false}，由 Python 侧决定放行还是跳过。
    const box = document.querySelector('.job-boss-info')
        || document.querySelector('.job-detail-box .boss-info')
        || document.querySelector('[class*="boss-info"]');
    if (!box) return JSON.stringify({ ok: false, reason: '未找到招聘者区块' });
    const text = (box.innerText || '').replace(/\s+/g, ' ').trim();
    if (!text) return JSON.stringify({ ok: false, reason: '招聘者区块为空' });
    return JSON.stringify({ ok: true, text: text.slice(0, 200) });
})()
