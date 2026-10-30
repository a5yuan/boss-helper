(() => {
    const panel = document.querySelector('.job-detail, .job-detail-box, .job-sec, [class*="detail"]');
    if (panel && panel.scrollHeight > panel.clientHeight) {
        let tick1 = Math.floor(Math.random() * 80) + 50;
        panel.scrollBy({ top: tick1, behavior: 'smooth' });
        setTimeout(() => {
            panel.scrollBy({ top: Math.floor(Math.random() * 60) + 40, behavior: 'smooth' });
        }, 800);
        setTimeout(() => {
            panel.scrollBy({ top: -Math.floor(Math.random() * 30), behavior: 'smooth' });
        }, 1800);
        return 'scrolled';
    }
    const candidates = document.querySelectorAll('[class*="detail"], [class*="content"], [class*="right"]');
    for (const el of candidates) {
        if (el.scrollHeight > el.clientHeight + 50) {
            el.scrollBy({ top: Math.floor(Math.random() * 80) + 50, behavior: 'smooth' });
            return 'scrolled_fallback';
        }
    }
    return 'no_panel';
})()
