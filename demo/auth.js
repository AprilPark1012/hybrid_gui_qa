/* demo 角色与登录（需求⑮ · 2026-09-28 晚）—— 所有页面共用的小工具（无构建步骤）
 *
 * 用法（每个页面两处）：
 *   ① <script src="auth.js"></script>（放在 vendor/vue 之后、页面自己的 <script> 之前）
 *   ② 页面里调用 DEMO_AUTH.init()；要控权限的元素加 data-perm="<action>"
 *
 * 口径：
 *   · token 存 localStorage("demo_token")，随请求以 `?token=` 带上（demo 简化；真系统应放 Cookie/Header）
 *   · 未登录访问受保护页面 ⇒ 自动跳 /login.html?next=<本页>
 *   · 权限不足 ⇒ 元素置灰 + 点击时给提示（服务端**同口径**再校验一遍，见 app.py 的 POST_ACTIONS 收口点）
 *   · 超管点右上角头像 ⇒ 可切换成 合同/订单/发票管理员（页面会重载，权限随之生效）
 */
(function () {
  const KEY = 'demo_token';
  const ACTION_LABEL = {
    create_contract: '新建合同', create_order: '新建订单',
    create_invoice: '创建发票', create_customer: '新建客户',
    view_contract: '查看合同', view_order: '查看订单', view_invoice: '查看发票',
  };
  const ROLE_LABEL = {
    contract_admin: '合同管理员', order_admin: '订单管理员',
    invoice_admin: '发票管理员', super_admin: '超级管理员',
  };

  // 需求㉓：页脚角落显示 build 版本号 —— 万一又出现「怎么还是老页面」，
  // 一眼就能看出浏览器手上这份是哪个版本（旧版页面没这行字样）
  async function showBuild() {
    try {
      const h = await (await fetch('/api/health', { cache: 'no-store' })).json();
      if (!h || !h.build) return;
      let el = document.getElementById('demo-build');
      if (!el) {
        el = document.createElement('div');
        el.id = 'demo-build';
        el.style.cssText = 'position:fixed;right:6px;bottom:4px;z-index:9999;font:11px/1.4 monospace;' +
                           'color:#9aa0a6;background:rgba(255,255,255,.85);border:1px solid #e2e4e8;' +
                           'border-radius:3px;padding:1px 6px;pointer-events:none';
        (document.body || document.documentElement).appendChild(el);
      }
      el.textContent = 'build ' + h.build;
    } catch (e) { /* 拿不到就算了，绝不因为版本标记影响页面 */ }
  }

  const A = {
    token: localStorage.getItem(KEY) || '',
    me: null,
    ROLE_LABEL, ACTION_LABEL,

    setToken(t) {
      this.token = t || '';
      if (t) localStorage.setItem(KEY, t); else localStorage.removeItem(KEY);
    },
    /* ---- 两种身份来源 ----
       ① 正常登录：localStorage 里的 token（随 URL 以 ?token= 带上）
       ② **自动化直连**（框架 / 用例 / 二类脚本）：URL 上给 `?demo_role=<角色>` —— 页面就以该角色渲染，
          且后续所有接口都带上同样的参数（服务端 Handler._auth 认它）。页面上**没有**这个入口，
          它只是让自动化不必先过登录页（真相见台账：登录页会打断 probe / 场景 / 录像键）。 */
    demoRole() {
      return (new URLSearchParams(location.search).get('demo_role') || '').trim();
    },
    /* 给 URL 带上身份（页面自己的 ?w=<分区> 由调用方先拼好） */
    url(path) {
      const r = this.demoRole();
      if (r) return path + (path.indexOf('?') >= 0 ? '&' : '?') + 'demo_role=' + encodeURIComponent(r);
      if (!this.token) return path;
      return path + (path.indexOf('?') >= 0 ? '&' : '?') + 'token=' + encodeURIComponent(this.token);
    },
    async api(path, opts) {
      const o = opts || {};
      o.headers = Object.assign({ 'Content-Type': 'application/json' }, o.headers || {});
      return fetch(this.url(path), o);
    },
    async load() {
      const t = new URLSearchParams(location.search).get('token');   // 支持 ?token= 直接带入（跨页跳转/自动化都方便）
      if (t) this.setToken(t);
      try {
        const r = await fetch(this.url('/api/me'));
        if (r.status === 401) { this.me = null; return null; }
        this.me = await r.json();
        return this.me;
      } catch (e) { this.me = null; return null; }
    },
    can(action) { return !!(this.me && this.me.can && this.me.can[action]); },
    isLoggedIn() { return !!this.me; },
    loginUrl() {
      return '/login.html?next=' + encodeURIComponent(location.pathname + location.search);
    },
    /* 页面间跳转带上身份（订单详情/合同详情/开票页之间的跳转用） */
    href(path) { return this.url(path); },
    /* 需求㚀：`?demo_role=` 直连的兜底 —— 给所有 <a> 跳转自动补上 demo_role。
       为什么需要：真实登录用户靠 localStorage 的 token 跳页不掉登录；而**自动化/演示**用
       `?demo_role=` 直连时，页面里硬编码的 href（「查看订单」「返回」、订单/合同编号链接…）
       都不带身份 ⇒ 一跳就掉 login.html（2026-09-29 实测：「去开票」跳到
       login.html?next=%2Finvoice_create.html…）。这里一处兜底，事件委托覆盖**动态渲染**的 a。 */
    patchLinks() {
      if (!this.demoRole()) return;
      document.addEventListener('click', (ev) => {
        const a = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
        if (!a) return;
        const raw = a.getAttribute('href') || '';
        if (!raw || raw.charAt(0) === '#' || raw.indexOf('javascript:') === 0) return;
        if (raw.indexOf('demo_role=') >= 0) return;
        let u;
        try { u = new URL(raw, location.href); } catch (e) { return; }
        if (u.origin !== location.origin) return;                 // 外链不动
        u.searchParams.set('demo_role', this.demoRole());
        a.setAttribute('href', u.pathname + '?' + u.searchParams.toString());
      }, true);                                                    // capture：先改 href 再让默认行为发生
    },
    async login(username, password) {
      const r = await fetch('/api/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) return d;
      this.setToken(d.token);
      this.me = d;
      return d;
    },
    async logout() {
      try { await this.api('/api/logout', { method: 'POST', body: JSON.stringify({ token: this.token }) }); } catch (e) {}
      this.setToken('');
      this.me = null;
      location.href = '/login.html';
    },
    async switchRole(role) {
      const r = await this.api('/api/switch_role', { method: 'POST', body: JSON.stringify({ role }) });
      const d = await r.json().catch(() => ({}));
      if (r.ok) { this.me = d; location.reload(); }        // 重载 ⇒ 页面按新角色重新渲染权限
      else { this.toast(d.error || '切换角色失败'); }
      return d;
    },

    /* ---- 弹出框 tips（需求⑱：所有校验/提示信息统一走这里）----
       为什么要「弹出框」而不是底部状态行：状态行在页面底部、容易被忽略；改成顶部居中的浮层卡片，
       带类型色（info 蓝 / warn 橙 / error 红 / ok 绿），3 秒自动消失，点一下立刻关掉。
       ⚠️ 状态行**同时保留同样的文字**（自动化判据与用例按状态行取值，见各页的 watch）—— */
    toast(msg, ms) { return window.DEMO_TIPS.show(msg, { ms }); },

    /* ---- 按 data-perm 统一置灰 + 点击拦截 ---- */
    applyGating(root) {
      const scope = root || document;
      scope.querySelectorAll('[data-perm]').forEach((el) => {
        const action = el.getAttribute('data-perm');
        const ok = this.can(action);
        el.classList.toggle('perm-off', !ok);
        el.setAttribute('aria-disabled', String(!ok));
        // ⚠️ 需求⑱：**故意不设 el.disabled** —— 浏览器不给 disabled 的按钮派发 click，
        //    那样用户点了既没反应也看不到原因；改成「置灰外观(.perm-off) + aria-disabled + 点击拦截弹 tips」。
        if (el.tagName === 'BUTTON' || (el.tagName === 'INPUT' && el.type !== 'checkbox')) el.disabled = false;
        if (!el._permHooked) {
          el._permHooked = true;
          el.addEventListener('click', (ev) => {
            if (this.can(el.getAttribute('data-perm'))) return;
            ev.preventDefault(); ev.stopPropagation();
            const custom = el.getAttribute('data-perm-tip');
            const label = ACTION_LABEL[el.getAttribute('data-perm')] || '该操作';
            const me = this.me;
            const msg = custom || (`当前角色「${me ? me.role_label : '未登录'}」没有${label}权限` +
                      (me && me.is_super ? '（可用右上角头像切换角色）' : ''));
            window.DEMO_TIPS.show(msg, { type: 'warn' });     // 弹出框提示
          }, true);
        }
      });
    },

    /* ---- 右上角头像（含超管切换角色 / 退出登录）---- */
    mountTopbar(hostId) {
      const host = document.getElementById(hostId || 'nav-user');
      if (!host || !this.me) return;
      const me = this.me;
      const items = [];
      if (me.is_super) {
        ['contract_admin', 'order_admin', 'invoice_admin'].forEach((r) => {
          if (r === me.role) return;
          items.push(`<button class="nu-item" data-switch="${r}">切换为${ROLE_LABEL[r]}</button>`);
        });
      }
      if (me.is_super && me.role !== 'super_admin') {
        items.push('<button class="nu-item" data-switch="super_admin">切回超级管理员</button>');
      }
      items.push('<button class="nu-item" data-act="logout">退出登录</button>');
      host.innerHTML =
        `<span class="nu-who">${me.user || ''} · ${me.role_label}</span>` +
        `<button class="nu-avatar" id="nu-avatar" title="点击${me.is_super ? '切换角色 / ' : ''}退出登录">` +
        `${(me.role_label || '?').slice(0, 1)}</button>` +
        `<div class="nu-menu" id="nu-menu" style="display:none">${items.join('')}</div>`;
      const menu = document.getElementById('nu-menu');
      document.getElementById('nu-avatar').addEventListener('click', (e) => {
        e.stopPropagation();
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
      });
      document.addEventListener('click', () => { menu.style.display = 'none'; });
      menu.addEventListener('click', (e) => {
        const sw = e.target.getAttribute && e.target.getAttribute('data-switch');
        if (sw) { this.switchRole(sw); return; }
        if (e.target.getAttribute && e.target.getAttribute('data-act') === 'logout') this.logout();
      });
    },

    /* ---- 样式自带（各页面不必改 CSS）---- */
    injectCss() {
      if (document.getElementById('demo-auth-css')) return;
      const s = document.createElement('style');
      s.id = 'demo-auth-css';
      s.textContent = `
  .nav-user { position: relative; display: flex; align-items: center; gap: 8px; margin-left: 8px; }
  .nav-user .nu-who { font-size: 12px; color: #4b5058; }
  .nav-user .nu-avatar { width: 28px; height: 28px; border-radius: 50%; border: 1px solid #1668dc;
                         background: #1668dc; color: #fff; cursor: pointer; font: 13px/1 system-ui; }
  .nav-user .nu-menu { position: absolute; right: 0; top: 34px; z-index: 60; background: #fff;
                       border: 1px solid #e2e4e8; border-radius: 4px; box-shadow: 0 4px 12px rgba(0,0,0,.10);
                       min-width: 168px; padding: 4px 0; }
  .nav-user .nu-item { display: block; width: 100%; text-align: left; border: 0; background: #fff;
                       padding: 7px 12px; font: 13px/1.4 inherit; color: #1f2329; cursor: pointer; }
  .nav-user .nu-item:hover { background: #f0f6ff; }
  .perm-off, .btn.perm-off { background: #f5f5f5 !important; color: #b0b4bb !important;
                             border-color: #e2e4e8 !important; cursor: not-allowed !important; }
  a.perm-off { opacity: .45; pointer-events: auto; }
      `;
      document.head.appendChild(s);
    },

    /* ---- 页面入口：加载身份 → 未登录跳登录页 → 置灰 + 挂头像 ---- */
    async init(opts) {
      showBuild();          // 需求㉓：角落显示 build —— 一眼判断手上这份是不是新版页面（旧版没这行）
      const o = opts || {};
      this.injectCss();
      const me = await this.load();
      if (!me) {
        if (o.allowAnonymous || this.demoRole()) { this.applyGating(); this.patchLinks(); return null; }
        location.href = this.loginUrl();
        return null;
      }
      this.applyGating();
      this.patchLinks();          // 需求㚀：跳转兜底带身份（demo_role 直连模式）
      this.mountTopbar(o.host);
      return me;
    },
  };

  /* ================= 弹出框 tips（需求⑱）=================
     用法：DEMO_TIPS.show('校验不通过的原因' [, {type:'error'|'warn'|'ok'|'info', ms:3000}])
     实现：单例浮层（顶部居中），新消息顶掉旧消息；点击立即关闭；自动消失（默认 3s）。 */
  const TIP_COLORS = {
    info:  ['#e6f4ff', '#1668dc', '#91caff'],
    ok:    ['#f6ffed', '#389e0d', '#b7eb8f'],
    warn:  ['#fffbe6', '#d48806', '#ffe58f'],
    error: ['#fff2f0', '#cf1322', '#ffccc7'],
  };
  window.DEMO_TIPS = {
    show(msg, opts) {
      const o = opts || {};
      const text = String(msg == null ? '' : msg);
      if (!text) return;
      let el = document.getElementById('demo-tip');
      if (!el) {
        el = document.createElement('div');
        el.id = 'demo-tip';
        el.style.cssText = 'position:fixed;left:50%;top:18px;transform:translateX(-50%);z-index:99999;' +
          'min-width:240px;max-width:80vw;padding:10px 16px;border-radius:6px;border:1px solid;' +
          'box-shadow:0 6px 18px rgba(0,0,0,.14);font:13px/1.6 system-ui,"Microsoft YaHei",sans-serif;' +
          'cursor:pointer;white-space:pre-wrap;word-break:break-all;';
        el.title = '点击关闭';
        el.addEventListener('click', () => { el.style.display = 'none'; });
        document.body.appendChild(el);
      }
      const type = o.type || (/(失败|错误|未登录|没有|不能|拦截|不存在|请先|请填写|必填|未保存|不对)/.test(text) ? 'error'
                   : (/(已创建|已保存|已新增|已关闭|已完成|成功|已提交|已新建|已还原|已重置|已全部加载)/.test(text) ? 'ok' : 'info'));
      const [bg, fg, bd] = TIP_COLORS[type] || TIP_COLORS.info;
      el.style.background = bg;
      el.style.color = fg;
      el.style.borderColor = bd;
      el.textContent = '💬 ' + text;
      el.style.display = 'block';
      clearTimeout(el._t);
      el._t = setTimeout(() => { el.style.display = 'none'; }, o.ms || 3000);
    },
    hide() { const el = document.getElementById('demo-tip'); if (el) el.style.display = 'none'; },
  };

  window.DEMO_AUTH = A;
})();
