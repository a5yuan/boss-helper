/* 真执行 src/js 下的探针：
   读源码 → 按 src/core/js_loader.py 的规则做纯字符串替换 → 在 node:vm
   沙箱里注入 window / document / location 运行 → 解析返回的 JSON。 */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const JS_DIR = path.resolve(HERE, '..', '..', 'src', 'js');

export function loadProbe(name, subs = {}) {
  let code = fs.readFileSync(path.join(JS_DIR, name), 'utf8');
  for (const [key, value] of Object.entries(subs)) {
    code = code.split(key).join(String(value));
  }
  return code;
}

export function runProbe(name, {
  state = {},
  document,
  href = 'https://www.zhaopin.com/jobs/?jl=653&kw=Java',
  subs = {},
  windowExtras = {},
} = {}) {
  if (!document) throw new Error('runProbe 需要 document（用 dom.mjs 的 makeDocument）');
  const code = loadProbe(name, subs);
  const window = { __INITIAL_STATE__: state, ...windowExtras };
  const location = { href };
  const sandbox = { window, document, location };
  const raw = vm.runInNewContext(code, sandbox, { filename: name });
  if (typeof raw !== 'string') {
    throw new Error(`${name} 返回的不是 JSON 字符串，而是 ${typeof raw}`);
  }
  try {
    return JSON.parse(raw);
  } catch (error) {
    throw new Error(`${name} 返回的不是合法 JSON: ${raw}`);
  }
}
