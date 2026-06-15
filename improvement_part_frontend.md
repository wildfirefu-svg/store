# 玄机子 · 八字命理 AI —— 前端改进方案

---

## 3.1 性能优化

### 3.1.1 代码分割与懒加载

#### 当前问题分析

项目当前采用原生 ES6 模块化方式，所有 JS 模块（`api.js`、`state.js`、`markdown.js`、`render-bazi.js`、`render-ziwei.js`、`ui.js`、`stream.js`）在 `index.html` 中通过 `<script type="module">` 一次性全部加载。这导致：

- **首屏加载时间过长**：用户首次访问时需下载全部模块代码，即使用户当前只需要基础对话功能。
- **紫微斗数模块浪费带宽**：`render-ziwei.js` 体积较大（包含星曜排盘算法），但多数用户主要使用八字功能。
- **ECharts 等可视化库**（引入后）体积约 800KB，会严重拖慢首屏。
- **无按需加载机制**：所有功能模块在应用启动时即完成初始化，浪费 CPU 资源。

#### 详细改进方案

**方案一：基于动态 `import()` 的路由级懒加载**

创建模块加载器，根据用户操作按需加载功能模块：

```javascript
// lazy-loader.js —— 动态模块加载器
// 使用动态 import() 实现按需加载，减少首屏 JS 体积

/**
 * 模块缓存映射表
 * 避免重复加载已下载的模块
 */
const moduleCache = new Map();

/**
 * 通用模块加载函数
 * @param {string} moduleName - 模块名称
 * @param {Function} importFn - 动态导入函数
 * @returns {Promise<Module>} 加载完成的模块
 */
export async function loadModule(moduleName, importFn) {
  // 如果模块已缓存，直接返回
  if (moduleCache.has(moduleName)) {
    return moduleCache.get(moduleName);
  }

  // 显示加载状态提示
  const loadingEvent = new CustomEvent('module:loading', {
    detail: { name: moduleName }
  });
  document.dispatchEvent(loadingEvent);

  try {
    // 动态导入模块
    const module = await importFn();
    moduleCache.set(moduleName, module);

    // 通知加载完成
    const loadedEvent = new CustomEvent('module:loaded', {
      detail: { name: moduleName }
    });
    document.dispatchEvent(loadedEvent);

    return module;
  } catch (error) {
    console.error(`[懒加载] 模块 "${moduleName}" 加载失败:`, error);
    throw error;
  }
}

/**
 * 预加载模块（空闲时执行）
 * 利用 requestIdleCallback 在浏览器空闲时段预加载非关键模块
 * @param {string} moduleName - 模块名称
 * @param {Function} importFn - 动态导入函数
 */
export function preloadModule(moduleName, importFn) {
  if (moduleCache.has(moduleName)) return;

  const idleCallback = window.requestIdleCallback || ((cb) => setTimeout(cb, 1));
  idleCallback(async () => {
    try {
      const module = await importFn();
      moduleCache.set(moduleName, module);
      console.log(`[预加载] 模块 "${moduleName}" 预加载完成`);
    } catch {
      // 预加载失败不影响正常使用，忽略错误
    }
  });
}
```

**方案二：功能模块懒加载集成**

改造主入口文件，将重型模块改为按需加载：

```javascript
// app.js —— 主入口（改造后）
import { StateManager } from './state.js';
import { ApiClient } from './api.js';
import { StreamHandler } from './stream.js';
import { loadModule, preloadModule } from './lazy-loader.js';

class App {
  constructor() {
    this.state = new StateManager();
    this.api = new ApiClient();
    this.stream = new StreamHandler();
    this.initialized = false;
  }

  /**
   * 应用初始化 —— 仅加载核心模块
   * 紫微斗数、可视化等模块延迟到用户触发时才加载
   */
  async init() {
    // 第一步：加载核心 UI 模块
    const { UIController } = await import('./ui.js');
    this.ui = new UIController(this.state);

    // 第二步：加载 Markdown 渲染（对话核心功能）
    const { MarkdownRenderer } = await import('./markdown.js');
    this.markdown = new MarkdownRenderer();

    // 第三步：加载八字排盘（主要功能，优先加载）
    const { BaziRenderer } = await import('./render-bazi.js');
    this.baziRenderer = new BaziRenderer();

    // 绑定 UI 事件
    this._bindEvents();
    this.initialized = true;

    // 第四步：空闲时预加载非关键模块
    this._preloadHeavyModules();
  }

  /**
   * 空闲时预加载重型模块
   */
  _preloadHeavyModules() {
    // 预加载紫微斗数模块（约 200KB）
    preloadModule('ziwei', () => import('./render-ziwei.js'));
    // 预加载报告导出模块
    preloadModule('export', () => import('./export-report.js'));
    // 预加载可视化模块
    preloadModule('charts', () => import('./charts.js'));
  }

  /**
   * 绑定 UI 事件 —— 按需加载触发
   */
  _bindEvents() {
    // 用户切换到紫微斗数时才加载对应模块
    this.ui.on('switch-to-ziwei', async (personId) => {
      const { ZiweiRenderer } = await loadModule(
        'ziwei',
        () => import('./render-ziwei.js')
      );
      this.ziweiRenderer = new ZiweiRenderer();
      this.ziweiRenderer.render(this.state.getPerson(personId));
    });

    // 用户请求导出报告时才加载导出模块
    this.ui.on('export-report', async (format, personId) => {
      const { ReportExporter } = await loadModule(
        'export',
        () => import('./export-report.js')
      );
      const exporter = new ReportExporter();
      await exporter.export(format, this.state.getPerson(personId));
    });

    // 用户查看可视化图表时才加载 ECharts
    this.ui.on('show-charts', async (personId) => {
      const { ChartManager } = await loadModule(
        'charts',
        () => import('./charts.js')
      );
      this.chartManager = new ChartManager();
      this.chartManager.render(this.state.getPerson(personId));
    });
  }
}

// 启动应用
const app = new App();
app.init();
```

**方案三：`<link rel="modulepreload">` 预加载关键模块**

```html
<!-- index.html 头部 —— 预加载关键模块 -->
<!-- 核心模块使用 modulepreload，浏览器会在解析阶段就开始下载 -->
<link rel="modulepreload" href="/js/state.js" />
<link rel="modulepreload" href="/js/api.js" />
<link rel="modulepreload" href="/js/stream.js" />
<link rel="modulepreload" href="/js/ui.js" />

<!-- 非关键模块使用 prefetch，在空闲时下载 -->
<link rel="prefetch" href="/js/render-ziwei.js" />
<link rel="prefetch" href="/js/charts.js" />
<link rel="prefetch" href="/js/export-report.js" />
```

#### 实施步骤

1. **创建 `lazy-loader.js`**：实现通用模块加载器，包含缓存、加载状态通知、预加载功能。
2. **改造 `app.js` 主入口**：将静态 `import` 改为动态 `import()`，核心模块保留静态导入。
3. **修改 `index.html`**：添加 `modulepreload` 和 `prefetch` 链接。
4. **添加加载状态 UI**：在模块加载期间显示轻量级加载指示器。
5. **测试验证**：使用 Chrome DevTools 的 Network 面板确认模块按需加载。

#### 预期收益

- 首屏 JS 体积减少约 **40-55%**（紫微斗数、图表、导出模块延迟加载）。
- 首次可交互时间（TTI）缩短约 **0.8-1.5 秒**。
- 低带宽用户体验显著改善，非关键功能模块按需下载。

---

### 3.1.2 Service Worker 离线缓存策略

#### 当前问题分析

- 应用无任何离线支持，网络断开后完全不可用。
- 用户已输入的命主数据在断网后无法查看。
- 静态资源（CSS、字体、SVG 图标）每次都需重新请求。
- 弱网环境下页面加载缓慢，用户体验差。

#### 详细改进方案

```javascript
// sw.js —— Service Worker 离线缓存策略
// 采用 "Stale-While-Revalidate" + "Cache-First" 混合策略

// 缓存版本号 —— 更新缓存时递增此值
const CACHE_VERSION = 'xjz-v1';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const DYNAMIC_CACHE = `${CACHE_VERSION}-dynamic`;

/**
 * 静态资源列表 —— 应用核心文件
 * 在 install 阶段预缓存这些文件
 */
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/css/theme.css',
  '/css/layout.css',
  '/css/components.css',
  '/js/state.js',
  '/js/api.js',
  '/js/stream.js',
  '/js/ui.js',
  '/js/markdown.js',
  '/js/render-bazi.js',
  '/js/app.js',
  '/js/lazy-loader.js',
  '/assets/icons/logo.svg',
  '/assets/fonts/noto-sans-sc.woff2'
];

/**
 * 安装阶段 —— 预缓存核心静态资源
 */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      // addAll 具有原子性：全部成功或全部失败
      return cache.addAll(STATIC_ASSETS);
    }).then(() => {
      // 跳过等待阶段，立即激活
      return self.skipWaiting();
    })
  );
});

/**
 * 激活阶段 —— 清理旧版本缓存
 */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name.startsWith('xjz-') && name !== STATIC_CACHE && name !== DYNAMIC_CACHE)
          .map((name) => caches.delete(name))
      );
    }).then(() => {
      // 立即接管所有客户端
      return self.clients.claim();
    })
  );
});

/**
 * 请求拦截 —— 根据请求类型采用不同缓存策略
 */
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // 策略一：API 请求 —— 仅网络（不走缓存，保证数据实时性）
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkOnly(request));
    return;
  }

  // 策略二：SSE 流式请求 —— 仅网络
  if (request.headers.get('accept')?.includes('text/event-stream')) {
    event.respondWith(networkOnly(request));
    return;
  }

  // 策略三：静态资源 —— 缓存优先（Cache First）
  if (isStaticAsset(url)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // 策略四：HTML 页面 —— 网络优先，回退到缓存（Network First）
  if (request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(networkFirst(request, DYNAMIC_CACHE));
    return;
  }

  // 策略五：其他资源 —— 过时优先重新验证（Stale-While-Revalidate）
  event.respondWith(staleWhileRevalidate(request, DYNAMIC_CACHE));
});

/**
 * 缓存优先策略 —— 优先返回缓存，缓存未命中时请求网络
 * 适用于：不常变动的静态资源（JS/CSS/字体/图标）
 */
async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // 网络失败且无缓存，返回离线页面
    return createOfflineResponse();
  }
}

/**
 * 网络优先策略 —— 优先请求网络，失败时回退到缓存
 * 适用于：HTML 页面（确保用户看到最新内容）
 */
async function networkFirst(request, cacheName) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch {
    const cached = await caches.match(request);
    return cached || createOfflineResponse();
  }
}

/**
 * 过时优先重新验证 —— 立即返回缓存，同时后台更新
 * 适用于：可能需要更新但又不想阻塞的资源
 */
async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cachedResponse = await cache.match(request);

  // 后台发起网络请求更新缓存
  const fetchPromise = fetch(request).then((networkResponse) => {
    if (networkResponse.ok) {
      cache.put(request, networkResponse);
    }
    return networkResponse;
  }).catch(() => cachedResponse);

  // 立即返回缓存（不等待网络）
  return cachedResponse || fetchPromise;
}

/**
 * 仅网络策略
 * 适用于：API 请求、SSE 流
 */
async function networkOnly(request) {
  try {
    return await fetch(request);
  } catch (error) {
    return new Response(JSON.stringify({ error: '网络不可用' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

/**
 * 判断是否为静态资源
 */
function isStaticAsset(url) {
  return /\.(js|css|woff2?|ttf|svg|png|jpg|webp|ico)$/i.test(url.pathname);
}

/**
 * 创建离线响应
 */
function createOfflineResponse() {
  const html = `
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head><meta charset="UTF-8"><title>玄机子 - 离线</title></head>
    <body style="display:flex;justify-content:center;align-items:center;height:100vh;
                 background:#1a1a2e;color:#e0e0e0;font-family:sans-serif;">
      <div style="text-align:center">
        <h1>🔮 玄机子</h1>
        <p>当前无网络连接，请检查网络设置后重试。</p>
        <p>已缓存的命主数据仍可离线查看。</p>
        <button onclick="location.reload()" style="margin-top:16px;padding:8px 24px;
                background:#6c5ce7;color:#fff;border:none;border-radius:8px;cursor:pointer;">
          重新连接
        </button>
      </div>
    </body>
    </html>
  `;
  return new Response(html, {
    headers: { 'Content-Type': 'text/html; charset=utf-8' }
  });
}
```

**Service Worker 注册模块：**

```javascript
// sw-register.js —— Service Worker 注册与更新管理
export class ServiceWorkerManager {
  constructor() {
    this.registration = null;
  }

  /**
   * 注册 Service Worker
   */
  async register() {
    // 检查浏览器是否支持 Service Worker
    if (!('serviceWorker' in navigator)) {
      console.warn('[SW] 当前浏览器不支持 Service Worker');
      return;
    }

    try {
      this.registration = await navigator.serviceWorker.register('/sw.js', {
        scope: '/'
      });

      console.log('[SW] 注册成功，scope:', this.registration.scope);

      // 检测更新
      this.registration.addEventListener('updatefound', () => {
        const newWorker = this.registration.installing;
        newWorker.addEventListener('statechange', () => {
          if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
            // 有新版本可用，提示用户刷新
            this._showUpdateNotification();
          }
        });
      });

    } catch (error) {
      console.error('[SW] 注册失败:', error);
    }
  }

  /**
   * 显示更新提示
   */
  _showUpdateNotification() {
    // 通过自定义事件通知 UI 层显示更新提示
    document.dispatchEvent(new CustomEvent('sw:update-available'));
  }

  /**
   * 执行更新 —— 用户确认后刷新
   */
  async applyUpdate() {
    if (this.registration?.waiting) {
      this.registration.waiting.postMessage({ type: 'SKIP_WAITING' });
      window.location.reload();
    }
  }
}
```

#### 实施步骤

1. **创建 `sw.js`**：编写 Service Worker 主逻辑，实现四种缓存策略。
2. **创建 `sw-register.js`**：封装注册、更新检测、版本管理逻辑。
3. **在 `app.js` 中注册**：应用初始化后调用 `ServiceWorkerManager.register()`。
4. **配置离线页面**：创建友好的离线提示 HTML。
5. **测试离线场景**：使用 DevTools 的 Application 面板模拟离线状态。
6. **配置缓存版本管理**：更新静态资源时递增 `CACHE_VERSION`。

#### 预期收益

- 二次访问加载速度提升 **60-80%**（静态资源全部命中缓存）。
- 弱网环境下用户体验大幅改善，核心功能可离线使用。
- 已缓存命主数据在无网络时仍可浏览。
- 服务器带宽消耗降低约 **50%**。

---

### 3.1.3 虚拟滚动

#### 当前问题分析

- **命主列表**：当命主数量超过 100 人时，DOM 节点过多导致渲染卡顿。
- **对话消息区**：长对话（如连续多轮解读）中消息节点累积，滚动性能下降。
- **报告区**：长篇报告渲染时一次性创建大量 DOM 节点，初始渲染耗时。
- 当前使用 `overflow-y: auto` 的原生滚动，所有子元素都在 DOM 中。

#### 详细改进方案

```javascript
// virtual-scroll.js —— 通用虚拟滚动组件
// 仅渲染可视区域内的元素，大幅减少 DOM 节点数量

export class VirtualScroll {
  /**
   * @param {Object} options - 配置项
   * @param {HTMLElement} options.container - 滚动容器元素
   * @param {number} options.itemHeight - 每项固定高度（px）
   * @param {number} options.buffer - 上下缓冲区额外渲染的条目数
   * @param {Function} options.renderItem - 渲染单条目的函数
   * @param {Function} options.getTotalCount - 获取总条目数的函数
   */
  constructor(options) {
    this.container = options.container;
    this.itemHeight = options.itemHeight;
    this.buffer = options.buffer ?? 3;
    this.renderItem = options.renderItem;
    this.getTotalCount = options.getTotalCount;

    // 上一次滚动位置（用于优化）
    this._lastScrollTop = -1;
    // 已渲染的 DOM 节点映射
    this._renderedItems = new Map();

    this._init();
  }

  /**
   * 初始化虚拟滚动结构
   */
  _init() {
    // 创建撑开容器，用于维持正确的滚动条高度
    this._spacer = document.createElement('div');
    this._spacer.className = 'virtual-scroll-spacer';
    this._spacer.style.cssText = 'width: 1px; pointer-events: none;';
    this.container.appendChild(this._spacer);

    // 创建可视区域容器，使用 absolute 定位
    this._viewport = document.createElement('div');
    this._viewport.className = 'virtual-scroll-viewport';
    this._viewport.style.cssText = `
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      will-change: transform;
    `;
    this.container.appendChild(this._viewport);

    // 容器设置为相对定位
    this.container.style.position = 'relative';
    this.container.style.overflow = 'auto';

    // 绑定滚动事件（使用 passive 提升滚动性能）
    this._onScroll = this._throttle(this._update.bind(this), 16); // 约 60fps
    this.container.addEventListener('scroll', this._onScroll, { passive: true });

    // 初始渲染
    this._update();
  }

  /**
   * 核心更新逻辑 —— 根据滚动位置计算并渲染可视区域
   */
  _update() {
    const scrollTop = this.container.scrollTop;
    // 如果滚动位置未变化，跳过更新
    if (scrollTop === this._lastScrollTop) return;
    this._lastScrollTop = scrollTop;

    const totalCount = this.getTotalCount();
    const containerHeight = this.container.clientHeight;

    // 计算可视范围
    const startIndex = Math.max(0, Math.floor(scrollTop / this.itemHeight) - this.buffer);
    const visibleCount = Math.ceil(containerHeight / this.itemHeight);
    const endIndex = Math.min(totalCount - 1, startIndex + visibleCount + this.buffer * 2);

    // 更新撑开容器高度（模拟完整列表高度）
    this._spacer.style.height = `${totalCount * this.itemHeight}px`;

    // 收集需要渲染的索引
    const neededIndices = new Set();
    for (let i = startIndex; i <= endIndex; i++) {
      neededIndices.add(i);
    }

    // 移除不在可视区域的旧节点
    for (const [index, element] of this._renderedItems) {
      if (!neededIndices.has(index)) {
        element.remove();
        this._renderedItems.delete(index);
      }
    }

    // 渲染新增的节点
    const fragment = document.createDocumentFragment();
    for (const index of neededIndices) {
      if (!this._renderedItems.has(index)) {
        const element = this.renderItem(index);
        element.style.cssText += `
          position: absolute;
          top: ${index * this.itemHeight}px;
          left: 0;
          width: 100%;
          height: ${this.itemHeight}px;
        `;
        fragment.appendChild(element);
        this._renderedItems.set(index, element);
      }
    }
    this._viewport.appendChild(fragment);
  }

  /**
   * 滚动到指定索引
   * @param {number} index - 目标索引
   */
  scrollToIndex(index) {
    this.container.scrollTop = index * this.itemHeight;
  }

  /**
   * 滚动到底部（用于新消息到达时自动滚动）
   */
  scrollToBottom() {
    const totalCount = this.getTotalCount();
    this.container.scrollTop = totalCount * this.itemHeight;
  }

  /**
   * 刷新渲染（数据变化后调用）
   */
  refresh() {
    this._lastScrollTop = -1;
    this._update();
  }

  /**
   * 销毁虚拟滚动实例
   */
  destroy() {
    this.container.removeEventListener('scroll', this._onScroll);
    this._renderedItems.clear();
    this.container.innerHTML = '';
  }

  /**
   * 节流函数 —— 限制更新频率
   */
  _throttle(fn, delay) {
    let lastCall = 0;
    return (...args) => {
      const now = Date.now();
      if (now - lastCall >= delay) {
        lastCall = now;
        fn(...args);
      }
    };
  }
}
```

**命主列表集成示例：**

```javascript
// person-list.js —— 命主列表虚拟滚动集成
import { VirtualScroll } from './virtual-scroll.js';
import { state } from './state.js';

export class PersonList {
  constructor(container) {
    this.container = container;
    this.virtualScroll = null;
  }

  /**
   * 初始化命主列表（使用虚拟滚动）
   */
  init() {
    this.virtualScroll = new VirtualScroll({
      container: this.container,
      itemHeight: 64, // 每个命主条目高度 64px
      buffer: 5,      // 上下各多渲染 5 条
      renderItem: (index) => this._renderPersonItem(index),
      getTotalCount: () => state.getPersonList().length
    });

    // 监听命主列表变化，刷新虚拟滚动
    state.on('person-list-changed', () => {
      this.virtualScroll.refresh();
    });
  }

  /**
   * 渲染单个命主条目
   */
  _renderPersonItem(index) {
    const person = state.getPersonList()[index];
    const item = document.createElement('div');
    item.className = 'person-item';
    item.setAttribute('role', 'listitem');
    item.setAttribute('aria-label', `命主：${person.name}`);
    item.dataset.personId = person.id;

    item.innerHTML = `
      <div class="person-item__avatar">${person.name.charAt(0)}</div>
      <div class="person-item__info">
        <span class="person-item__name">${this._escapeHtml(person.name)}</span>
        <span class="person-item__date">${person.birthDate || '未设置'}</span>
      </div>
    `;

    // 点击选中命主
    item.addEventListener('click', () => {
      state.selectPerson(person.id);
    });

    return item;
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}
```

**对话消息区集成示例：**

```javascript
// message-list.js —— 对话消息虚拟滚动
import { VirtualScroll } from './virtual-scroll.js';

export class MessageList {
  constructor(container) {
    this.container = container;
    this.messages = [];
    // 对话消息高度不固定，使用动态高度模式
    this.virtualScroll = null;
  }

  /**
   * 初始化消息列表
   * 注意：对话消息高度不固定，需要特殊处理
   */
  init() {
    // 对于高度不固定的消息列表，使用分段虚拟滚动
    // 将消息按固定高度分段，每段内包含若干完整消息
    this.virtualScroll = new VirtualScroll({
      container: this.container,
      itemHeight: 120, // 预估平均消息高度
      buffer: 3,
      renderItem: (index) => this._renderMessageSegment(index),
      getTotalCount: () => this._getSegmentCount()
    });
  }

  /**
   * 添加新消息并自动滚动到底部
   */
  addMessage(message) {
    this.messages.push(message);
    this.virtualScroll.refresh();
    this.virtualScroll.scrollToBottom();
  }

  _getSegmentCount() {
    return this.messages.length;
  }

  _renderMessageSegment(index) {
    const message = this.messages[index];
    const element = document.createElement('div');
    element.className = `message message--${message.role}`;
    element.innerHTML = message.content;
    return element;
  }
}
```

#### 实施步骤

1. **创建 `virtual-scroll.js`**：实现通用虚拟滚动核心类。
2. **改造命主列表**：将 `person-list` 区域的原生渲染替换为虚拟滚动。
3. **改造对话消息区**：集成消息列表的虚拟滚动，处理动态高度问题。
4. **添加 CSS 样式**：为虚拟滚动容器和条目添加必要样式。
5. **性能测试**：使用 500+ 命主、1000+ 消息的场景测试滚动流畅度。

#### 预期收益

- DOM 节点数量从 O(n) 降至 O(可视区域)，始终保持在 **30-50 个节点**。
- 命主列表滚动帧率从 24fps 提升至稳定 **60fps**。
- 长对话场景内存占用降低 **70%** 以上。

---

### 3.1.4 资源预加载与预连接

#### 当前问题分析

- 未使用 `<link rel="preconnect">` 预连接 API 服务器，每次请求需额外进行 DNS 查询和 TLS 握手。
- 字体文件在 CSS 解析后才开始加载，导致文字闪烁（FOIT/FOUT）。
- 背景图片和装饰性 SVG 无预加载，页面加载过程中出现视觉跳跃。
- 未利用 `<link rel="dns-prefetch">` 预解析外部域名。

#### 详细改进方案

```html
<!-- index.html <head> 区域 —— 资源预加载优化 -->
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>玄机子 · 八字命理 AI</title>

  <!-- ===== 预连接：提前建立与关键域名的连接 ===== -->
  <!-- API 服务器：预连接可节省 100-500ms（DNS + TCP + TLS） -->
  <link rel="preconnect" href="https://api.xuanjizi.com" crossorigin />
  <link rel="dns-prefetch" href="https://api.xuanjizi.com" />

  <!-- CDN 资源预连接（如果使用 CDN 托管 ECharts 等库） -->
  <link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin />
  <link rel="dns-prefetch" href="https://cdn.jsdelivr.net" />

  <!-- ===== 关键资源预加载 ===== -->
  <!-- 核心 CSS 预加载 -->
  <link rel="preload" href="/css/theme.css" as="style" />
  <link rel="preload" href="/css/layout.css" as="style" />

  <!-- 字体预加载 —— 消除 FOIT/FOUT -->
  <link rel="preload" href="/assets/fonts/noto-sans-sc-regular.woff2" as="font"
        type="font/woff2" crossorigin />
  <link rel="preload" href="/assets/fonts/noto-sans-sc-bold.woff2" as="font"
        type="font/woff2" crossorigin />

  <!-- 核心 JS 模块预加载 -->
  <link rel="modulepreload" href="/js/app.js" />
  <link rel="modulepreload" href="/js/state.js" />
  <link rel="modulepreload" href="/js/api.js" />

  <!-- Logo SVG 预加载（首屏可见） -->
  <link rel="preload" href="/assets/icons/logo.svg" as="image" />

  <!-- ===== 非关键资源预取（空闲时下载） ===== -->
  <link rel="prefetch" href="/js/render-ziwei.js" as="script" />
  <link rel="prefetch" href="/js/charts.js" as="script" />
  <link rel="prefetch" href="/assets/icons/bazi-wheel.svg" as="image" />

  <!-- ===== 样式表 ===== -->
  <link rel="stylesheet" href="/css/theme.css" />
  <link rel="stylesheet" href="/css/layout.css" />
  <link rel="stylesheet" href="/css/components.css" />
</head>
```

**字体加载优化 —— 使用 `font-display: swap`：**

```css
/* fonts.css —— 字体加载优化 */
@font-face {
  font-family: 'NotoSansSC';
  src: url('/assets/fonts/noto-sans-sc-regular.woff2') format('woff2');
  font-weight: 400;
  font-style: normal;
  /* swap: 先用系统字体显示，自定义字体加载完成后替换 */
  font-display: swap;
}

@font-face {
  font-family: 'NotoSansSC';
  src: url('/assets/fonts/noto-sans-sc-bold.woff2') format('woff2');
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}

/* 使用 CSS 自定义属性统一管理字体 */
:root {
  --font-primary: 'NotoSansSC', -apple-system, BlinkMacSystemFont,
                  'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
}
```

**智能预加载调度器：**

```javascript
// preload-scheduler.js —— 智能资源预加载调度
// 根据用户行为预测并预加载可能需要的资源

export class PreloadScheduler {
  constructor() {
    this.preloaded = new Set();
    this.observers = [];
  }

  /**
   * 初始化预加载调度
   * 监听用户行为模式，智能预加载
   */
  init() {
    // 监听鼠标悬停 —— 用户即将点击的元素相关资源预加载
    document.addEventListener('mouseover', (e) => {
      const target = e.target.closest('[data-preload]');
      if (target) {
        const resources = target.dataset.preload.split(',');
        resources.forEach((resource) => this.preload(resource.trim()));
      }
    }, { passive: true });

    // 页面空闲 3 秒后预加载高概率使用的资源
    const idleCallback = window.requestIdleCallback || ((cb) => setTimeout(cb, 3000));
    idleCallback(() => {
      this._preloadCommonResources();
    }, { timeout: 5000 });
  }

  /**
   * 预加载单个资源
   */
  preload(url) {
    if (this.preloaded.has(url)) return;
    this.preloaded.add(url);

    const link = document.createElement('link');
    link.rel = 'prefetch';
    link.href = url;
    link.as = this._guessResourceType(url);
    document.head.appendChild(link);
  }

  /**
   * 预加载常用资源
   */
  _preloadCommonResources() {
    const commonResources = [
      '/js/render-bazi.js',      // 八字排盘（最常用功能）
      '/js/markdown.js',         // Markdown 渲染
      '/assets/icons/bazi-wheel.svg' // 命盘图标
    ];
    commonResources.forEach((url) => this.preload(url));
  }

  /**
   * 推断资源类型
   */
  _guessResourceType(url) {
    if (/\.js$/i.test(url)) return 'script';
    if (/\.css$/i.test(url)) return 'style';
    if (/\.(woff2?|ttf|otf)$/i.test(url)) return 'font';
    if (/\.(png|jpg|jpeg|gif|svg|webp)$/i.test(url)) return 'image';
    return 'fetch';
  }
}
```

#### 实施步骤

1. **修改 `index.html`**：添加 `preconnect`、`dns-prefetch`、`preload`、`modulepreload` 标签。
2. **创建 `fonts.css`**：配置 `font-display: swap`，优化字体加载策略。
3. **创建 `preload-scheduler.js`**：实现智能预加载调度器。
4. **添加 `data-preload` 属性**：在 UI 元素上标注关联资源，支持悬停预加载。
5. **性能度量**：使用 Lighthouse 和 Web Vitals 对比优化前后的 LCP、FCP 指标。

#### 预期收益

- 首屏关键资源加载时间（LCP）缩短 **200-500ms**。
- 字体闪烁（FOIT）完全消除。
- API 请求延迟降低 **100-300ms**（省去 DNS + TCP + TLS 时间）。
- Lighthouse Performance 评分提升 **10-20 分**。

---

### 3.1.5 图片与 SVG 优化

#### 当前问题分析

- 命盘图表使用内联 SVG 字符串拼接，未做优化，DOM 节点冗余。
- 装饰性图标使用 PNG 格式，体积大且不支持缩放。
- 未使用现代图片格式（WebP/AVIF），带宽浪费。
- 缺少图片懒加载机制，首屏外的图片也在加载。
- SVG 未压缩，包含编辑器冗余数据。

#### 详细改进方案

**SVG 雪碧图方案：**

```javascript
// svg-sprite.js —— SVG 图标雪碧图管理
// 将所有图标合并为一个 SVG 雪碧图，减少 HTTP 请求

export class SvgSprite {
  constructor() {
    // 图标注册表
    this.icons = new Map();
    this._spriteElement = null;
  }

  /**
   * 初始化 SVG 雪碧图
   * 在页面中注入隐藏的 SVG 容器
   */
  init() {
    // 创建隐藏的 SVG 容器
    const svg = document.createElement('svg');
    svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    svg.setAttribute('aria-hidden', 'true');
    svg.style.cssText = `
      position: absolute;
      width: 0;
      height: 0;
      overflow: hidden;
    `;

    // 将所有图标定义注入 <defs>
    const defs = document.createElement('defs');
    for (const [name, pathData] of this.icons) {
      const symbol = document.createElementNS('http://www.w3.org/2000/svg', 'symbol');
      symbol.setAttribute('id', `icon-${name}`);
      symbol.setAttribute('viewBox', '0 0 24 24');

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', pathData);
      path.setAttribute('fill', 'currentColor');

      symbol.appendChild(path);
      defs.appendChild(symbol);
    }

    svg.appendChild(defs);
    document.body.insertBefore(svg, document.body.firstChild);
    this._spriteElement = svg;
  }

  /**
   * 注册图标路径数据
   * @param {string} name - 图标名称
   * @param {string} pathData - SVG path 数据
   */
  register(name, pathData) {
    this.icons.set(name, pathData);
  }

  /**
   * 创建图标元素
   * @param {string} name - 图标名称
   * @param {number} size - 图标尺寸（px）
   * @returns {SVGElement} SVG 图标元素
   */
  createIcon(name, size = 24) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', size);
    svg.setAttribute('height', size);
    svg.setAttribute('aria-hidden', 'true');
    svg.classList.add('icon');

    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttributeNS('http://www.w3.org/1999/xlink', 'xlink:href', `#icon-${name}`);
    svg.appendChild(use);

    return svg;
  }
}

// 图标实例与常用图标注册
export const svgSprite = new SvgSprite();

// 注册常用图标（精简的 path 数据）
svgSprite.register('bazi', 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z');
svgSprite.register('ziwei', 'M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z');
svgSprite.register('person', 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z');
svgSprite.register('export', 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z');
svgSprite.register('share', 'M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92 1.61 0 2.92-1.31 2.92-2.92s-1.31-2.92-2.92-2.92z');
svgSprite.register('dark-mode', 'M9.37 5.51A7.35 7.35 0 0 0 9.1 7.5c0 4.08 3.32 7.4 7.4 7.4.68 0 1.35-.09 1.99-.27A7.014 7.014 0 0 1 12 19c-3.86 0-7-3.14-7-7 0-2.93 1.81-5.45 4.37-6.49zM12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z');
```

**图片懒加载指令：**

```javascript
// lazy-image.js —— 图片懒加载管理
// 使用 IntersectionObserver 实现高性能图片懒加载

export class LazyImageManager {
  constructor() {
    this.observer = null;
  }

  /**
   * 初始化懒加载观察器
   */
  init() {
    this.observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const img = entry.target;
            this._loadImage(img);
            this.observer.unobserve(img);
          }
        });
      },
      {
        // 提前 200px 开始加载（用户滚动时更流畅）
        rootMargin: '200px 0px'
      }
    );

    // 观察所有带 data-src 的图片
    document.querySelectorAll('img[data-src]').forEach((img) => {
      this.observer.observe(img);
    });
  }

  /**
   * 加载单张图片
   */
  _loadImage(img) {
    const src = img.dataset.src;
    const srcset = img.dataset.srcset;

    if (src) {
      img.src = src;
    }
    if (srcset) {
      img.srcset = srcset;
    }

    // 加载完成后添加淡入动画
    img.classList.add('lazy-loaded');
    img.removeAttribute('data-src');
    if (srcset) img.removeAttribute('data-srcset');
  }

  /**
   * 动态添加懒加载图片
   */
  observe(imgElement) {
    if (this.observer) {
      this.observer.observe(imgElement);
    }
  }
}
```

**CSS 图片优化样式：**

```css
/* image-optimization.css —— 图片优化相关样式 */

/* 图片懒加载淡入效果 */
img[data-src] {
  opacity: 0;
  transition: opacity 0.3s ease-in;
}

img.lazy-loaded {
  opacity: 1;
}

/* 响应式图片容器（保持宽高比，防止布局偏移 CLS） */
.image-container {
  position: relative;
  overflow: hidden;
  /* 默认 16:9 宽高比 */
  aspect-ratio: 16 / 9;
  background-color: var(--color-bg-tertiary, #2a2a3e);
}

.image-container img {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* SVG 图标统一样式 */
.icon {
  display: inline-block;
  vertical-align: middle;
  fill: currentColor;
  /* 防止 SVG 图标被选中 */
  pointer-events: none;
}

/* 命盘 SVG 优化 —— 使用 will-change 提升合成性能 */
.bazi-chart svg,
.ziwei-chart svg {
  will-change: transform;
  /* 启用 GPU 加速 */
  transform: translateZ(0);
}
```

**SVG 压缩与优化工具链：**

```json
// package.json 中添加 SVG 优化脚本（开发时运行）
{
  "scripts": {
    "svg:optimize": "svgo --config=svgo.config.js -f ./src/assets/svg -o ./dist/assets/svg",
    "svg:sprite": "svg-sprite --config=svg-sprite.config.json ./src/assets/svg/*.svg"
  },
  "devDependencies": {
    "svgo": "^3.0.0"
  }
}
```

```javascript
// svgo.config.js —— SVGO 压缩配置
module.exports = {
  plugins: [
    // 移除编辑器冗余数据
    { name: 'removeEditorsNSData' },
    // 移除空属性
    { name: 'removeEmptyAttrs' },
    // 移除空容器
    { name: 'removeEmptyContainers' },
    // 合并路径
    { name: 'mergePaths' },
    // 转换坐标为相对值（减小体积）
    { name: 'convertPathData', params: { makeArcs: { threshold: 2.5 } } },
    // 移除不可见元素
    { name: 'removeHiddenElems' },
    // 压缩数字精度
    { name: 'convertTransform' },
    // 移除 title（无障碍由代码处理）
    { name: 'removeTitle' }
  ]
};
```

#### 实施步骤

1. **创建 `svg-sprite.js`**：将所有图标整合为 SVG 雪碧图，通过 `<use>` 引用。
2. **创建 `lazy-image.js`**：实现基于 IntersectionObserver 的图片懒加载。
3. **添加图片优化 CSS**：淡入动画、响应式容器、GPU 加速。
4. **配置 SVGO**：压缩所有 SVG 文件，移除冗余数据。
5. **替换现有图标**：将 `<img>` 图标替换为 SVG 雪碧图引用。
6. **添加 `data-src` 属性**：为所有非首屏图片添加懒加载支持。

#### 预期收益

- HTTP 请求数减少 **60-80%**（图标合并为雪碧图）。
- SVG 文件体积减少 **30-50%**（SVGO 压缩）。
- 首屏外图片延迟加载，首屏加载时间减少 **200-400ms**。
- 消除图片导致的布局偏移（CLS 降至 0）。

---
