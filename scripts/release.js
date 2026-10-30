import { execSync } from "child_process";
import readline from "readline";

// 终端颜色辅助
const colors = {
  reset: "\x1b[0m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  red: "\x1b[31m",
  cyan: "\x1b[36m",
  gray: "\x1b[90m",
};

// 解析命令行参数 (例如 --version/-v 0.2.2 --desc/-d "修复问题")
function parseArgs() {
  const args = process.argv.slice(2);
  const parsed = {
    version: null,
    desc: null,
    silent: false,
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "--version" || arg === "-v") {
      parsed.version = args[i + 1];
      i++;
    } else if (arg === "--desc" || arg === "-d") {
      parsed.desc = args[i + 1];
      i++;
    } else if (arg === "--silent" || arg === "-s") {
      parsed.silent = true;
    }
  }

  // 如果同时传了版本和描述，自动开启静默一键发布
  if (parsed.version && parsed.desc) {
    parsed.silent = true;
  }

  return parsed;
}

function runCmd(cmd) {
  console.log(`${colors.gray}> ${cmd}${colors.reset}`);
  return execSync(cmd, { stdio: "inherit" });
}

async function main() {
  const cliArgs = parseArgs();

  console.log(`${colors.cyan}===================================================`);
  console.log("          BOSS Helper 全自动多端开源发布 CLI");
  console.log(`===================================================${colors.reset}\n`);

  let rl = null;
  let version = cliArgs.version;
  let desc = cliArgs.desc;

  try {
    // 1. 检查当前分支状态
    const currentBranch = execSync("git branch --show-current").toString().trim();
    if (currentBranch !== "main") {
      console.error(`${colors.red}❌ 错误: 必须在 'main' 分支上运行此发布脚本。当前分支为: ${currentBranch}${colors.reset}`);
      process.exit(1);
    }

    const status = execSync("git status --porcelain").toString().trim();
    // 排除运行 release.js 本身的变动（如果我们在提交前运行测试它的话）
    if (status && !status.includes("release.js") && !status.includes("package.json")) {
      console.warn(`${colors.yellow}⚠️ 警告: 本地 main 分支存在未提交的修改，请先提交或暂存后再发布。${colors.reset}`);
      console.log(status);
      process.exit(1);
    }

    // 2. 获取上一次公开的 Release Commit SHA 用于 soft reset
    let lastReleaseCommit = "";
    try {
      lastReleaseCommit = execSync("git rev-parse origin/main-release").toString().trim();
    } catch {
      try {
        lastReleaseCommit = execSync("git rev-parse main-release").toString().trim();
      } catch {
        console.error(`${colors.red}❌ 错误: 找不到本地或远程的 'main-release' 分支记录。${colors.reset}`);
        process.exit(1);
      }
    }

    console.log(`${colors.green}✓ 工作区状态检查通过。${colors.reset}`);
    console.log(`${colors.gray}上一次发布的基准 commit 为: ${lastReleaseCommit}${colors.reset}\n`);

    // 3. 如果不是静默模式，启动交互提问
    if (!cliArgs.silent) {
      rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
      });

      const askQuestion = (query) => new Promise((resolve) => rl.question(query, resolve));

      if (!version) {
        version = (await askQuestion(`${colors.yellow}请输入要发布的新版本号 (例如 0.2.2): ${colors.reset}`)).trim();
      }
      if (!desc) {
        desc = (await askQuestion(`${colors.yellow}请输入该版本的更新简述 (例如 修复列表残影与抽屉选中): ${colors.reset}`)).trim();
      }
    }

    if (!version || !desc) {
      console.error(`${colors.red}❌ 错误: 必须提供版本号 and 更新简述！${colors.reset}`);
      process.exit(1);
    }

    const commitMsg = `release: v${version} - ${desc}`;

    console.log(`\n${colors.cyan}即将执行以下发布操作：`);
    console.log(`1. 将 main 分支最新修改推送至 GitHub (origin) 和 Gitee (gitee)`);
    console.log(`2. 切换至 main-release 分支`);
    console.log(`3. 强制对齐 main 状态并软回退到 ${lastReleaseCommit.substring(0, 7)}`);
    console.log(`4. 统一提交 commit: "${commitMsg}"`);
    console.log(`5. 打上 Tag v${version}`);
    console.log(`6. 强制推送 main-release 和 Tag 至 GitHub 和 Gitee`);
    console.log(`7. 自动切回 main 分支`);
    console.log(`===================================================${colors.reset}\n`);

    // 如果不是静默模式，需要用户手动输入 y 确认
    if (rl) {
      const askQuestion = (query) => new Promise((resolve) => rl.question(query, resolve));
      const confirm = (await askQuestion("确认无误并执行发布吗？(y/N): ")).trim().toLowerCase();
      if (confirm !== "y" && confirm !== "yes") {
        console.log(`${colors.yellow}发布已取消。${colors.reset}`);
        process.exit(0);
      }
    } else {
      console.log(`${colors.yellow}检测到命令行参数，已开启一键静默自动发布模式...${colors.reset}\n`);
    }

    console.log(`\n${colors.green}[1/7] 推送 main 分支至 GitHub 和 Gitee...${colors.reset}`);
    runCmd("git push origin main");
    runCmd("git push gitee main");

    console.log(`\n${colors.green}[2/7] 切换至 main-release 分支...${colors.reset}`);
    runCmd("git checkout main-release");

    console.log(`\n${colors.green}[3/7] 强行对齐 main 状态并软回退到上个版本...${colors.reset}`);
    runCmd("git reset --hard main");
    runCmd(`git reset --soft ${lastReleaseCommit}`);

    console.log(`\n${colors.green}[4/7] 提交发布包 commit...${colors.reset}`);
    runCmd(`git commit -m "${commitMsg}"`);

    console.log(`\n${colors.green}[5/7] 创建本地 Tag v${version}...${colors.reset}`);
    try {
      execSync(`git tag -d v${version}`, { stdio: "ignore" });
    } catch {}
    runCmd(`git tag -a v${version} -m "${commitMsg}"`);

    console.log(`\n${colors.green}[6/7] 强制推送 main-release 和 Tag v${version} 到 GitHub 和 Gitee...${colors.reset}`);
    runCmd("git push origin main-release -f");
    runCmd("git push gitee main-release -f");
    runCmd(`git push origin v${version} -f`);
    runCmd(`git push gitee v${version} -f`);

    console.log(`\n${colors.green}[7/7] 正在切回开发分支 main 并清理临时状态...${colors.reset}`);
    runCmd("git checkout main");

    console.log(`\n${colors.green}===================================================`);
    console.log(`🎉 恭喜！版本 v${version} 发布及多端同步已圆满完成！`);
    console.log(`===================================================${colors.reset}\n`);

  } catch (error) {
    console.error(`\n${colors.red}❌ 发布过程中出错:${colors.reset}`, error.message);
    try {
      execSync("git reset --hard HEAD", { stdio: "ignore" });
      execSync("git checkout main", { stdio: "ignore" });
      console.log(`${colors.yellow}已自动切回 main 开发分支并恢复工作区状态。${colors.reset}`);
    } catch {}
  } finally {
    if (rl) {
      rl.close();
    }
  }
}

main();
