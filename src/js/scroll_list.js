(async () => {
    const containers = document.querySelectorAll('.search-job-result, .job-list-box');
    const target = containers.length > 0 ? containers[0] : window;

    for (let i = 0; i < 8; i++) {
        const step = Math.floor(Math.random() * 80) + 100;
        if (target === window) {
            window.scrollBy({ top: step, behavior: 'smooth' });
        } else {
            target.scrollBy({ top: step, behavior: 'smooth' });
        }
        await new Promise(r => setTimeout(r, Math.random() * 300 + 150));
    }
    return 'scrolled';
})()
