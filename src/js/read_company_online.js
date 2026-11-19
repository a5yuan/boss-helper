(() => {
    // 同步 IIFE：只读本地 DOM / Vue，不发任何请求，任何情况都返回 JSON 字符串。
    const TARGET = '__SID__';
    const MAX_SCAN = 6000;  // 全页扫描上限，避免超大页面卡住 CDP

    // 固定键顺序：card_sel / row_sel / logo / logo_cls / span_scope / row_text_len / vue
    const makeEvidence = (cardSel, rowSel, logoFound, logoCls, spanScope, rowTextLen, vue) => ({
        card_sel: cardSel || '',
        row_sel: rowSel || '',
        logo: !!logoFound,
        logo_cls: String(logoCls || '').slice(0, 40),
        span_scope: spanScope || 'none',
        row_text_len: rowTextLen || 0,
        vue: (typeof vue === 'boolean') ? vue : null,
    });

    const fail = (reason, ev) => JSON.stringify({ ok: false, reason: reason, evidence: ev });

    // 从元素上的 Vue 实例取 propsData.data（与 click_vue.js 一致）
    const readVueData = (el) => {
        try {
            const vm = el && el.__vue__;
            if (!vm) return null;
            const pdRaw = vm.$options ? (vm.$options.propsData || vm.$props) : null;
            const pd = pdRaw ? (pdRaw.data || pdRaw) : null;
            return pd || null;
        } catch (e) {
            return null;
        }
    };

    try {
        let card = null;
        let cardSel = '';
        let vueData = null;

        // ① 优先 .job-card-box。Vue 实例可能挂在卡片本身，也可能挂在父节点
        //    （与 click_dom.js 的取法保持一致）。
        const boxes = document.querySelectorAll('.job-card-box');
        for (const el of boxes) {
            const pd = readVueData(el) || readVueData(el.parentElement);
            if (pd && pd.securityId === TARGET) {
                card = el; cardSel = '.job-card-box'; vueData = pd; break;
            }
        }

        // ② 再找 .job-card-wrap / .job-card，并记录命中的具体类名
        if (!card) {
            const list = document.querySelectorAll('.job-card-wrap,.job-card');
            for (const el of list) {
                const pd = readVueData(el) || readVueData(el.parentElement);
                if (pd && pd.securityId === TARGET) {
                    const cls = String(el.className || '');
                    card = el;
                    cardSel = cls.includes('job-card-wrap') ? '.job-card-wrap' : '.job-card';
                    vueData = pd;
                    break;
                }
            }
        }

        // ③ 兜底：有上限的全页扫描
        if (!card) {
            const all = document.querySelectorAll('*');
            const n = Math.min(all.length, MAX_SCAN);
            for (let i = 0; i < n; i++) {
                const el = all[i];
                const pd = readVueData(el);
                if (pd && pd.securityId === TARGET) {
                    card = el.closest('.job-card-box,.job-card-wrap,.job-card') || el;
                    cardSel = 'full_scan';
                    vueData = pd;
                    break;
                }
            }
        }

        if (!card) {
            return fail('card_not_found', makeEvidence('', '', false, '', 'none', 0, null));
        }

        // 公司行：a.boss-info 优先，退一步 .boss-info
        let row = card.querySelector('a.boss-info');
        let rowSel = row ? 'a.boss-info' : '';
        if (!row) {
            row = card.querySelector('.boss-info');
            if (row) rowSel = '.boss-info';
        }

        // logo 在 row 内找，找不到再退到 card
        let logo = row ? row.querySelector('.boss-logo') : null;
        if (!logo) logo = card.querySelector('.boss-logo');
        const logoFound = !!logo;
        const logoCls = logo ? String(logo.className || '') : '';

        // 在线图标：先在 logo 内找，再退到整张卡片
        const spanSel = '.boss-online-icon,[class*="boss-online"]';
        let span = null;
        let spanScope = 'none';
        if (logo) {
            span = logo.querySelector(spanSel);
            if (span) spanScope = 'logo';
        }
        if (!span) {
            span = card.querySelector(spanSel);
            if (span) spanScope = 'card';
        }

        // 公司行有文字说明行已渲染；没有文字说明行还是空的（或压根没有）
        const rowTextLen = row ? String(row.innerText || row.textContent || '').trim().length : 0;
        const vueOnline = (vueData && typeof vueData.bossOnline === 'boolean') ? vueData.bossOnline : null;

        const ev = makeEvidence(cardSel, rowSel, logoFound, logoCls, spanScope, rowTextLen, vueOnline);

        // 判定顺序：DOM 图标 > 公司行有文字即离线 > Vue 布尔字段兜底
        if (span) {
            return JSON.stringify({ ok: true, online: true, source: 'dom', evidence: ev });
        }
        if (row && rowTextLen > 0) {
            return JSON.stringify({ ok: true, online: false, source: 'dom', evidence: ev });
        }
        if (typeof vueOnline === 'boolean') {
            return JSON.stringify({ ok: true, online: vueOnline, source: 'vue', evidence: ev });
        }

        // 行在但没文字 → row_empty；连行都没找到 → logo_missing。两者都交给 Python 按未知放行。
        const reason = row ? 'row_empty' : 'logo_missing';
        return fail(reason, ev);
    } catch (e) {
        // 页面结构异常时返回明确失败，绝不向上抛，避免 Python 侧 json.loads 崩
        return fail('js_error', makeEvidence('', '', false, '', 'none', 0, null));
    }
})()
