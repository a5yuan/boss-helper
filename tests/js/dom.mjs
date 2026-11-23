/* 极简 DOM shim：只实现探针实际用到的部分。
   支持标签、.class、[attr]、[attr="v"]、[attr*="v"] 以及空格分隔的后代组合。
   所有尺寸由 opts.rect / width / height 控制，方便构造「不可见」元素。 */

function parseAttr(token) {
  const m = /^\[([\w-]+)(?:([*^$~|]?=)"?([^"\]]*)"?)?\]$/.exec(token);
  if (!m) throw new Error(`不支持的属性选择器: ${token}`);
  return { name: m[1], op: m[2] || null, value: m[3] ?? '' };
}

function parseSimple(text) {
  const m = /^([a-zA-Z][\w-]*)?((?:[.#][\w-]+|\[[^\]]*\])*)$/.exec(text);
  if (!m) throw new Error(`不支持的选择器: ${text}`);
  const simple = { tag: m[1] ? m[1].toUpperCase() : null, classes: [], attrs: [] };
  const tail = m[2] || '';
  const re = /([.#])([\w-]+)|(\[[^\]]*\])/g;
  let hit;
  while ((hit = re.exec(tail))) {
    if (hit[1] === '.') simple.classes.push(hit[2]);
    else if (hit[1] === '#') simple.attrs.push({ name: 'id', op: '=', value: hit[2] });
    else simple.attrs.push(parseAttr(hit[3]));
  }
  return simple;
}

function splitChain(selector) {
  const parts = [];
  let buf = '';
  let inBracket = false;
  for (const ch of selector.trim()) {
    if (ch === '[') inBracket = true;
    if (ch === ']') inBracket = false;
    if (/\s/.test(ch) && !inBracket) {
      if (buf) parts.push(buf);
      buf = '';
    } else {
      buf += ch;
    }
  }
  if (buf) parts.push(buf);
  return parts.map(parseSimple);
}

function matchesSimple(node, simple) {
  if (simple.tag && node.tagName !== simple.tag) return false;
  for (const c of simple.classes) {
    if (!node.classList.contains(c)) return false;
  }
  for (const a of simple.attrs) {
    const value = node.getAttribute(a.name);
    if (value === null) return false;
    if (a.op === '=' && value !== a.value) return false;
    if (a.op === '*=' && !value.includes(a.value)) return false;
    if (a.op === '^=' && !value.startsWith(a.value)) return false;
    if (a.op === '$=' && !value.endsWith(a.value)) return false;
    if (a.op === '~=' && !value.split(/\s+/).includes(a.value)) return false;
  }
  return true;
}

function matchesChain(node, chain) {
  if (!matchesSimple(node, chain[chain.length - 1])) return false;
  let cursor = node.parentElement;
  for (let i = chain.length - 2; i >= 0; i -= 1) {
    while (cursor && !matchesSimple(cursor, chain[i])) cursor = cursor.parentElement;
    if (!cursor) return false;
    cursor = cursor.parentElement;
  }
  return true;
}

function descendants(root) {
  const out = [];
  (function walk(node) {
    out.push(node);
    node.children.forEach(walk);
  })(root);
  return out;
}

function query(root, selector) {
  const chains = selector.split(',').map(splitChain);
  const nodes = descendants(root);
  return nodes.filter(node => chains.some(chain => matchesChain(node, chain)));
}

export class El {
  constructor(tag, opts = {}) {
    this.tagName = String(tag).toUpperCase();
    this.className = opts.className || '';
    this.id = opts.id || '';
    this.attrs = opts.attrs || {};
    this.children = [];
    this.parentElement = null;
    this.disabled = !!opts.disabled;
    this.scrollTop = opts.scrollTop || 0;
    this.scrollHeight = opts.scrollHeight ?? 1000;
    this.scrolledIntoView = 0;
    this._text = opts.text || '';
    this._rect = {
      left: opts.rect?.left ?? 0,
      top: opts.rect?.top ?? 0,
      width: opts.rect?.width ?? opts.width ?? 100,
      height: opts.rect?.height ?? opts.height ?? 30,
    };
    if (opts.value !== undefined || /^(TEXTAREA|INPUT)$/.test(this.tagName)) {
      this.value = opts.value ?? '';
    }
    this.classList = {
      contains: name => this.className.split(/\s+/).filter(Boolean).includes(name),
    };
    (opts.children || []).forEach(child => this.append(child));
  }

  append(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  get innerText() {
    const parts = this._text ? [this._text] : [];
    for (const child of this.children) {
      const text = child.innerText;
      if (text) parts.push(text);
    }
    return parts.join('\n');
  }

  get textContent() {
    const parts = this._text ? [this._text] : [];
    for (const child of this.children) {
      const text = child.textContent;
      if (text) parts.push(text);
    }
    return parts.join('');
  }

  getAttribute(name) {
    if (name === 'class') return this.className || null;
    if (name === 'id') return this.id || null;
    return Object.prototype.hasOwnProperty.call(this.attrs, name) ? String(this.attrs[name]) : null;
  }

  getBoundingClientRect() {
    // 父级不可见时子元素也拿不到尺寸（等价于 display:none 的实测结果）
    let node = this;
    while (node) {
      const rect = node._rect;
      if (!(rect.width > 0) || !(rect.height > 0)) {
        return { left: 0, top: 0, width: 0, height: 0, right: 0, bottom: 0 };
      }
      node = node.parentElement;
    }
    const { left, top, width, height } = this._rect;
    return { left, top, width, height, right: left + width, bottom: top + height };
  }

  scrollIntoView(options) {
    this.scrolledIntoView += 1;
    this.lastScrollOptions = options;
  }

  querySelectorAll(selector) {
    return query(this, selector).filter(node => node !== this);
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
}

export function el(tag, opts = {}) {
  return new El(tag, opts);
}

export function makeDocument(children = []) {
  const body = el('body', { children });
  const document = {
    body,
    querySelectorAll: selector => query(body, selector),
    querySelector: selector => query(body, selector)[0] || null,
  };
  return document;
}
