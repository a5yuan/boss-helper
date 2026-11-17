(() => {
    // 只定位「立即沟通 / 继续沟通」按钮并返回中心坐标，不点击。
    // 真正的点击交给 CDP Input.dispatchMouseEvent（原生点击才能触发 SPA 的处理器）。
    const vis = el => {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        if (r.width < 20 || r.height < 10) return false;
        const s = getComputedStyle(el);
        return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
    };
    const norm = el => (el.innerText || el.textContent || '').replace(/\s+/g, '');
    const TEXTS = ['立即沟通', '继续沟通'];
    const pick = root => {
        const byClass = Array.from(
            root.querySelectorAll('.btn-startchat,.op-btn-chat,[class*="startchat"],[class*="btn-chat"]')
        ).filter(vis);
        if (byClass.length) return byClass[0];
        const clickable = Array.from(root.querySelectorAll('a,button,[role="button"]'));
        let hits = clickable.filter(el => vis(el) && TEXTS.includes(norm(el)));
        if (!hits.length) {
            hits = Array.from(root.querySelectorAll('span,div')).filter(el => vis(el) && TEXTS.includes(norm(el)));
        }
        const inner = hits.filter(el => !hits.some(o => o !== el && el.contains(o)));
        return inner[0] || hits[0] || null;
    };
    const SCOPE_SELECTORS = [
        '.job-detail-container', '.job-detail-box', '.job-detail-content',
        '.job-detail', '.detail-content', '.job-detail-wrapper',
    ];
    let target = null;
    for (const sel of SCOPE_SELECTORS) {
        const root = document.querySelector(sel);
        if (!root) continue;
        target = pick(root);
        if (target) break;
    }
    if (!target) target = pick(document);
    if (!target) return JSON.stringify({ ok: false, reason: '未找到沟通按钮' });

    target.scrollIntoView({ block: 'center' });
    const r = target.getBoundingClientRect();
    return JSON.stringify({
        ok: true,
        text: norm(target).slice(0, 8),
        tag: target.tagName,
        x: Math.round(r.left + r.width / 2),
        y: Math.round(r.top + r.height / 2),
    });
})()
