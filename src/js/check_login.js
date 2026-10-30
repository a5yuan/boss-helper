(() => {
    // 扫描页面上所有的薪资字段，如果有 **** 则判定为未登录或会话过期
    const salaries = Array.from(document.querySelectorAll('.salary, .job-salary'));
    return salaries.some(s => s.innerText.includes('****'));
})()
