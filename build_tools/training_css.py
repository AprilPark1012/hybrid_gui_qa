# -*- coding: utf-8 -*-
"""培训页样式（从旧 build_html.py 抽出，V8.9.9 重构）。

[!] 单独一个模块的理由：页面结构与内容已经搬进 `training_content_*.py`，
样式留在这里 -> 改样式不必碰内容，内容也不必在 f-string 里跟大括号搏斗。
"""

CSS = r""":root {
    --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; --bg:#f1f5f9;
    --brand:#0891b2; --brand2:#2563eb; --star:#fbbf24;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;
          background:var(--bg); color:var(--ink); line-height:1.7; }
  .wrap { max-width:1080px; margin:0 auto; padding:0 20px; }

  /* hero */
  .hero { background:linear-gradient(135deg,#0f172a,#1e3a8a 60%,#0891b2);
           color:#fff; padding:56px 20px 40px; text-align:center; }
  .hero h1 { font-size:2.3rem; margin-bottom:10px; }
  .hero p { opacity:.85; font-size:1.12rem; max-width:760px; margin:8px auto; }
  .pill { display:inline-block; background:rgba(255,255,255,.15);
           border:1px solid rgba(255,255,255,.3); border-radius:999px;
           padding:5px 16px; margin:6px 4px; font-size:.92rem; }

  /* section */
  section { margin:38px 0; }
  .sec-title { font-size:1.5rem; margin-bottom:6px; display:flex; align-items:center; gap:10px; }
  .sec-title .n { background:var(--brand); color:#fff; width:32px; height:32px;
                   border-radius:8px; display:inline-flex; align-items:center;
                   justify-content:center; font-size:1.05rem; flex-shrink:0; }
  .sec-sub { color:var(--muted); margin-bottom:18px; }

  .card { background:#fff; border:1px solid var(--line); border-radius:14px;
           padding:22px; box-shadow:0 1px 3px rgba(15,23,42,.05); }

  /* 对比 */
  .vs { display:grid; grid-template-columns:1fr auto 1fr; gap:16px; align-items:center; }
  .vs-box { border-radius:12px; padding:18px; }
  .vs-box.ai { background:#eef2ff; border:2px solid #3b6fdd; }
  .vs-box.pw { background:#f0fdf4; border:2px solid #0f8f6a; }
  .vs-box h3 { margin-bottom:8px; font-size:1.05rem; }
  .vs-box ul { padding-left:18px; }
  .vs-box li { margin:4px 0; font-size:.95rem; }
  .plus { font-size:1.8rem; color:var(--brand); text-align:center; font-weight:700; }

  /* 流程 */
  .flow { display:flex; gap:10px; flex-wrap:wrap; }
  .flow-step { flex:1; min-width:180px; background:#fff; border:1px solid var(--line);
                border-top:4px solid var(--brand); border-radius:10px; padding:16px; }
  .flow-step .tag { font-size:.78rem; color:var(--muted); text-transform:uppercase;
                     letter-spacing:.5px; margin-bottom:4px; }
  .flow-step h4 { margin-bottom:4px; }
  .flow-step p { font-size:.9rem; color:var(--muted); }
  .flow-step .bdge { display:inline-block; font-size:.75rem; padding:2px 8px;
                      border-radius:6px; color:#fff; margin-bottom:8px; }

  /* 要点 */
  .pts { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; }
  .pt { border:1px solid var(--line); border-radius:12px; padding:16px; background:#fff; }
  .pt .ico { font-size:1.5rem; }
  .pt h4 { margin:6px 0 4px; }
  .pt p { font-size:.9rem; color:var(--muted); }
  .pt .code-inline { background:#0d1117; color:#7ee787; padding:2px 6px;
                      border-radius:5px; font-family:ui-monospace,monospace; font-size:.85em; }

  /* 调用关系树 */
  .tree { background:#0d1117; color:#d1d5db; border-radius:12px; padding:20px;
           font-family:ui-monospace,Consolas,monospace; font-size:.9rem; overflow-x:auto; }
  .tree b { color:#8ab4f8; }

  /* code card */
  .file-card { margin-bottom:22px; }
  .file-head { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
  .file-path { background:#f1f5f9; padding:4px 10px; border-radius:6px; font-size:.88rem; }
  .file-desc { color:var(--muted); font-size:.93rem; margin-bottom:12px; }
  .badge { color:#fff; font-size:.78rem; padding:3px 10px; border-radius:999px; }
  .codebox { background:#0d1117; border-radius:10px; overflow-x:auto; }
  .code-line { display:flex; font-family:ui-monospace,Consolas,monospace;
                font-size:.85rem; line-height:1.6; padding:1px 8px; }
  .code-line .ln { color:#3b475a; min-width:38px; text-align:right;
                    padding-right:12px; user-select:none; }
  .code-line code { white-space:pre; color:#e6edf3; }
  .code-line.star { background:#31250b; border-left:3px solid var(--star); }
  .code-line.star code { color:#fef3c7; font-weight:600; }
  .code-line.star .ln { color:#b78a2c; }
  .k { color:#ff7b72; } .s { color:#7ee787; } .c { color:#8b949e; font-style:italic; }
  .code-note { background:#fff7d6; border:1px solid #f5d76e; border-radius:8px;
                padding:8px 12px; margin:6px 0 10px; font-size:.9rem; }

  /* 坑 */
  .pit { border-left:4px solid #ef4444; background:#fef2f2; padding:14px 16px;
          border-radius:6px; margin-bottom:14px; }
  .pit h4 { color:#b91c1c; margin-bottom:4px; }
  .pit p { font-size:.92rem; color:#7f1d1d; }
  .pit code { background:#fecaca; color:#7f1d1d; padding:1px 5px; border-radius:4px;
               font-size:.87em; }

  /* command */
  .cmd { background:#0d1117; color:#e6edf3; border-radius:10px; padding:16px;
          font-family:ui-monospace,monospace; font-size:.9rem; overflow-x:auto; }
  .cmd .prompt { color:#4ade80; } .cmd .cmt { color:#8b949e; }

  /* 记住 */
  .mem { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }
  @media(max-width:760px){ .mem{grid-template-columns:1fr} .vs{grid-template-columns:1fr} }
  .mem-item { border-radius:12px; padding:22px; text-align:center; color:#fff; }
  .mem-item.a { background:#3b6fdd; } .mem-item.b { background:#0f8f6a; }
  .mem-item.c { background:#0891b2; }
  .mem-item .big { font-size:1.6rem; margin-bottom:6px; }
  .mem-item b { font-size:1.15rem; display:block; margin-bottom:6px; }
  .mem-item span { font-size:.9rem; opacity:.9; }

  /* 版本徽标 + 更新记录 */
  .ver { display:inline-block; margin:4px 0 10px; padding:5px 16px; border-radius:999px;
          background:rgba(255,255,255,.18); border:1px solid rgba(255,255,255,.42);
          color:#fff; font-weight:800; letter-spacing:.6px; font-size:.98rem; text-decoration:none; }
          .ver:hover { background:rgba(255,255,255,.3); }
  .card.cl { margin-bottom:16px; }
  .card.cl.cl-cur { border-color:var(--brand); box-shadow:0 0 0 3px rgba(8,145,178,.10); }
  .cl-head { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:6px; }
  .cl-ver { font-size:1.3rem; font-weight:800; color:var(--brand); }
  .cl-date { color:var(--muted); font-size:.88rem; }
  .cl-tag { background:var(--brand); color:#fff; font-size:.74rem; padding:3px 10px; border-radius:999px; }
  .cl-theme { color:var(--muted); font-size:.9rem; }
  .cl-sum { margin:4px 0 12px; }
  .cl-kind { display:flex; gap:10px; align-items:flex-start; margin:9px 0; }
  .cl-kind ul { margin:0; padding-left:20px; flex:1; }
  .cl-kind li { margin:5px 0; }
  .chip { flex:0 0 auto; font-size:.78rem; font-weight:700; padding:3px 10px; border-radius:999px; white-space:nowrap; }
  footer { text-align:center; color:var(--muted); padding:34px 0 40px; font-size:.88rem; }

  /* ===== 右侧章节大纲（TOC）+ 特性章 + 表格重排 + 打印（A4 纵向）===== */
  html { scroll-behavior:smooth; }
  [id] { scroll-margin-top:16px; }
  .shell { display:flex; align-items:flex-start; justify-content:center;
            gap:22px; max-width:1980px; margin:0 auto; padding:0 14px; }
  .shell .wrap { flex:1 1 auto; min-width:0; }
  #toc { position:sticky; top:14px; flex:0 0 296px; width:296px;
          max-height:calc(100vh - 28px); overflow:auto; background:#fff;
          border:1px solid var(--line); border-radius:12px; padding:12px 12px 16px;
          box-shadow:0 1px 3px rgba(15,23,42,.06); font-size:.86rem; }
  .toc-head { display:flex; align-items:center; justify-content:space-between;
               margin-bottom:8px; padding-bottom:8px; border-bottom:1px solid var(--line); }
  .toc-head b { font-size:.95rem; }
  .toc-btn { border:1px solid var(--line); background:#f8fafc; border-radius:6px;
              padding:2px 8px; font-size:.76rem; cursor:pointer; color:var(--muted); }
  #toc ul { list-style:none; margin:0; padding:0; }
  #toc li { margin:1px 0; }
  #toc a { display:block; color:var(--ink); text-decoration:none; border-radius:6px;
            padding:3px 6px; line-height:1.45; }
  #toc a:hover { background:#f1f5f9; }
  #toc a.active { background:#e0f2fe; color:#0e7490; font-weight:700; }
  #toc .tn { display:inline-block; min-width:16px; color:var(--brand); font-weight:700; }
  /* 层级：章(#toc .toc-l1) -> 子章节/特性(.toc-l2) -> 子特性(.toc-l3)
     [!] 必须带 `#toc` 前缀：上面的 #toc ul 规则是 ID 选择器，特异性高于裸类选择器，
         裸 .toc-l2 的 padding-left 会被静默吃掉 -> 缩进失效（只剩 border-left 生效，
         看起来三层一样重）。每下一层缩进 2 字符（约 13px），字号/字重/颜色三层递减。 */
  #toc .toc-l1 > li > a { font-size:.9rem; font-weight:700; color:var(--ink); }
  #toc .toc-l1 > li + li { border-top:1px solid #eef2f7; margin-top:4px; padding-top:4px; }
  #toc .toc-l2 { margin-left:6px; border-left:2px solid #dbe6f3; padding-left:2ch; }
  #toc .toc-l2 > li > a { font-size:.845rem; font-weight:600; color:#334155; }
  #toc .toc-l3 { display:none; margin-left:6px; border-left:1px dashed #dfe7f0; padding-left:2ch; }
  #toc .toc-l3.open { display:block; }
  #toc .toc-l3 a { font-size:.80rem; font-weight:400; color:#64748b; }
  #toc .toc-l3 > li > a::before { content:"· "; color:#cbd5e1; }
  #toc .toc-feat > a { font-weight:600; }
  .toc-caret { float:right; border:1px solid var(--line); background:#fff; border-radius:5px;
                width:20px; height:18px; line-height:1; font-size:.82rem; cursor:pointer;
                color:var(--muted); padding:0; }
  .toc-fab { position:fixed; right:14px; bottom:16px; z-index:40; display:none;
              background:var(--brand); color:#fff; border-radius:999px; padding:8px 14px;
              font-size:.86rem; box-shadow:0 2px 8px rgba(0,0,0,.22); cursor:pointer; }
  @media (max-width:1180px) {
    #toc { position:fixed; right:0; top:0; height:100vh; max-height:100vh; border-radius:0;
            width:300px; transform:translateX(105%); transition:transform .18s;
            z-index:60; box-shadow:-4px 0 18px rgba(15,23,42,.18); }
    #toc.open { transform:translateX(0); }
    .toc-fab { display:block; }
  }
  /* 表格：按纸宽重排（避免超宽横向滚动） */
  .tbl { width:100%; border-collapse:collapse; font-size:.86rem; margin:6px 0 14px; }
  .tbl th, .tbl td { border:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top; }
  .tbl th { background:#f1f5f9; }
  /* 特性章（第 6 章） */
  .feat { margin:22px 0 26px; }
  .feat-title { display:flex; align-items:center; gap:10px; flex-wrap:wrap; font-size:1.18rem;
                 border-bottom:2px solid var(--brand); padding-bottom:6px; margin-bottom:4px; }
  .feat-title .fno { background:var(--brand); color:#fff; border-radius:6px; padding:2px 9px; font-size:.82rem; }
  .feat-title .fkey { color:var(--muted); font-size:.78rem; font-family:ui-monospace,monospace; }
  .feat-goal { font-size:.92rem; margin-bottom:12px; }
  .subfeat { border-left:3px solid var(--line); padding:2px 0 2px 14px; margin:14px 0; }
  .subfeat-title { font-size:1rem; margin-bottom:4px; }
  .subfeat-title .sno { color:var(--brand2); font-family:ui-monospace,monospace; margin-right:6px; }
  .codesrc { font-size:.82rem; color:var(--muted); margin:3px 0; }
  .diffbox { background:#fff7ed; border:1px solid #fdba74; border-radius:8px; padding:8px 12px;
              margin:8px 0; font-size:.86rem; }
  .flow2 { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin:7px 0; }
  .fnode { background:#eef2ff; border:1px solid #c7d2fe; border-radius:7px;
            padding:4px 9px; font-size:.82rem; font-family:ui-monospace,monospace; }
  .fnode.g { background:#ecfdf5; border-color:#a7f3d0; }
  .fnode.y { background:#fefce8; border-color:#fde68a; }
  .fnode.r { background:#fef2f2; border-color:#fecaca; }
  .farrow { color:var(--brand); font-weight:700; }
  @page { size:A4 portrait; margin:12mm; }
  @media print {
    .shell { display:block; max-width:none; padding:0; }
    .shell .wrap { max-width:100%; margin:0; padding:0; }
    #toc, .toc-fab { display:none !important; }
    body { background:#fff; }
    .hero { padding:16px 10px 12px; }
    .hero h1 { font-size:1.5rem; }
    section { margin:14px 0; }
    .card { box-shadow:none; break-inside:avoid; }
    .subfeat { break-inside:avoid; }
    .tree, .cmd, .codebox { overflow:visible !important; white-space:pre-wrap; word-break:break-word; font-size:8.4pt; }
    .tbl { font-size:8.4pt; }
    .tbl th, .tbl td { padding:4px 5px; }
    a { color:inherit; text-decoration:none; }
  }
  /* ---- V8.9.9 重构新增 ---- */
  .lead { font-size:1.06rem; color:#334155; }
  .kv { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }
  .kv .box { background:#fff; border:1px solid var(--line); border-radius:12px; padding:16px; }
  .kv .box b { display:block; margin-bottom:4px; }
  .kv .box span { font-size:.92rem; color:var(--muted); }
  details { background:#fff; border:1px solid var(--line); border-radius:12px;
             padding:12px 16px; margin:12px 0; }
  details > summary { cursor:pointer; font-weight:600; color:var(--brand2); }
  details[open] > summary { margin-bottom:10px; }
  details .inner { padding-top:6px; }
  .fault { width:100%; border-collapse:collapse; font-size:.92rem; }
  .fault th, .fault td { border:1px solid var(--line); padding:8px 10px; text-align:left; vertical-align:top; }
  .fault th { background:#f8fafc; }
  .fault td:first-child { white-space:nowrap; font-family:ui-monospace,monospace; font-size:.86rem; color:#b91c1c; }
  .ok { color:#0f8f6a; font-weight:600; }
  .bad { color:#b91c1c; font-weight:600; }
  .step { background:#fff; border:1px solid var(--line); border-left:4px solid var(--brand);
           border-radius:10px; padding:14px 16px; margin:10px 0; }
  .step .sn { display:inline-block; background:var(--brand); color:#fff; border-radius:6px;
               padding:1px 8px; font-size:.82rem; margin-right:8px; }
  .tag2 { display:inline-block; font-size:.76rem; padding:1px 7px; border-radius:5px;
           background:#e0f2fe; color:#075985; margin-left:6px; }
  .warn-tip { background:#fffbeb; border:1px solid #fcd34d; border-radius:8px; padding:10px 14px; margin:10px 0; }
  .ok-tip { background:#ecfdf5; border:1px solid #6ee7b7; border-radius:8px; padding:10px 14px; margin:10px 0; }
  .bad-tip { background:#fef2f2; border:1px solid #fca5a5; border-radius:8px; padding:10px 14px; margin:10px 0; }
"""
