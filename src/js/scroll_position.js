(() => {
    const containers = document.querySelectorAll('.search-job-result, .job-list-box');
    if (containers.length > 0) {
        const c = containers[0];
        return JSON.stringify({scrollTop: Math.round(c.scrollTop), scrollHeight: c.scrollHeight, clientHeight: c.clientHeight});
    }
    return JSON.stringify({scrollTop: Math.round(window.scrollY), scrollHeight: document.body.scrollHeight, clientHeight: window.innerHeight});
})()
