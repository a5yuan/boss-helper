(() => {
    // 点击详情面板 / 详情页上的「立即沟通」按钮，打开聊天窗口。
    // 依赖页面结构：按钮文本为「立即沟通」或「继续沟通」，常见类名 btn-startchat / op-btn-chat。
    // 优先在详情容器里找，避免误点左侧列表其他卡片的按钮。
    // 页面结构变化时返回 {ok:false, reason}，由 Python 侧决定是否重试。
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
        // ① 类名优先，命中即返回，避免遍历整页
        const byClass = Array.from(
            root.querySelectorAll('.btn-startchat,.op-btn-chat,[class*="startchat"],[class*="btn-chat"]')
        ).filter(vis);
        if (byClass.length) return byClass[0];

        // ② 文本匹配：先看链接/按钮，再退回任意元素；取最内层，避免点到外层容器
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

    if (!target) {
        return JSON.stringify({ ok: false, reason: '未找到「立即沟通」按钮' });
    }

    try {
        target.scrollIntoView({ block: 'center' });
        target.click();
    } catch (e) {
        return JSON.stringify({ ok: false, reason: '点击失败: ' + (e && e.message ? e.message : e) });
    }

    return JSON.stringify({
        ok: true,
        text: norm(target).slice(0, 8),
        tag: target.tagName,
        cls: String(target.className || '').slice(0, 60),
    });
})()
