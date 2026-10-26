#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIDLC 文档预览（可选）—— 把 `开发文档/` 打成一个**自包含**的文档站

生成物全部落在 `开发文档/_汇总/` 里，整个目录可以打包带走：

    _汇总/
    ├── index.html          入口
    ├── _sidebar.md         侧边栏
    ├── 状态.md …           9 个汇总视图
    ├── vendor/             docsify.min.js + vue.css（从技能 assets 复制）
    ├── docs/               CR 原文快照（01需求 / 02缺陷 / 03技术债）
    └── 如何预览.txt         给对方的一句话说明

用法
    python 开发文档/04技能/aidlc/scripts/预览.py               # 生成 + 起服务（Ctrl+C 停）
    python 开发文档/04技能/aidlc/scripts/预览.py --port 9000
    python 开发文档/04技能/aidlc/scripts/预览.py --host 0.0.0.0  # 同一内网的同事也能看
    python 开发文档/04技能/aidlc/scripts/预览.py --no-serve     # 只生成，打包用

为什么要把依赖复制进 `_汇总/`（而不是从技能目录读）：
  1. 打包要自包含 —— 只发 `_汇总/` 就能看，不依赖技能副本在不在；
  2. 服务根因此可以**只有 `_汇总/`** —— 不需要 `/s/`、`/d/`、`/v/` 那种手工路由，
     直接用标准库静态服务，安全边界天然是这一个目录。
代价：`docs/` 是**快照**，改了源文档要重跑本脚本（输出里会提醒）。

为什么 Docsify 要本地化：它默认从 CDN 拉 JS，内网/断网时**白屏且无报错**，
而 AIDLC 的典型场景就是内网。资源跟着技能走。
"""

import argparse
import functools
import http.server
import io
import os
import shutil
import socket
import socketserver
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# 不生成 __pycache__：技能副本是只读资源（同 汇总.py / 自检.py 的理由）
sys.dont_write_bytecode = True

SKILL_DIR = os.path.dirname(HERE)                 # …/aidlc
ASSETS = os.path.join(SKILL_DIR, 'assets')
SUM_NAME = '_汇总'
KIND_DIRS = ('01需求', '02缺陷', '03技术债')
KIND_LABEL = {'01需求': '需求', '02缺陷': '缺陷', '03技术债': '技术债'}
VENDOR_FILES = ('docsify.min.js', 'vue.css')

# 侧边栏里每条 CR 的子文档顺序（未列出的排后面）
DOC_ORDER = ('需求.md', '问题.md', '状态.md', '验收报告.md', '测试记录.md',
             '决策记录.md', '变更说明.md', '运维说明.md', '构建说明.md')

INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(title)s · 开发文档</title>
<!-- 全部用相对路径：整个 _汇总/ 目录可以整体搬走，不依赖外部 -->
<link rel="stylesheet" href="vendor/vue.css">
<style>
  /* 表格多（状态表 5~6 列），版心放宽、字号收一点，否则「负责人」会被挤成竖排 */
  .markdown-section { max-width: none; }
  .markdown-section table { display: table; width: auto; min-width: 100%%; font-size: 13px; }
  .markdown-section table td, .markdown-section table th { vertical-align: top; }
  .markdown-section table td:first-child, .markdown-section table th:first-child { white-space: nowrap; }
  /* 第 3 列（状态表=负责人 / 索引表=性质）常被长文本列挤到只有 1 个字宽。
     只设下限，不用 nowrap —— 长列该换行还是换行。 */
  .markdown-section table td:nth-child(3), .markdown-section table th:nth-child(3) { min-width: 4.5em; }
  .markdown-section code { white-space: pre-wrap; }
  .markdown-section .docsify-copy-code-button { font-size: 12px; }
  .sidebar { width: 260px; }
  body.close .sidebar { transform: translateX(-260px); }
</style>
</head>
<body>
<div id="app">加载中…（若一直停在这里，检查 vendor/docsify.min.js 是否完整）</div>
<script>
  window.$docsify = {
    name: %(name_js)s,
    basePath: './',
    // 注意：选项名是 homepage（不是 home）—— 写错会静默去加载 README.md → 404
    homepage: '状态.md',
    loadSidebar: '_sidebar.md',
    subMaxLevel: 2,
    maxLevel: 4,
    auto2top: true,
    relativePath: false,
    search: false
  };
</script>
<script src="vendor/docsify.min.js"></script>
</body>
</html>
"""

HOWTO = """这份目录是 AIDLC 生成的文档站，内容自包含，可以整体拷走。

看之前需要一个本地静态服务（浏览器直接用 file:// 打开读不了 md，会被拦）：

    cd 本目录
    python -m http.server 8090
    然后浏览器打开 http://127.0.0.1:8090/

也可以直接用技能脚本起（会顺带重新生成一遍）：

    python <技能副本>/scripts/预览.py

注意
- 这里是**生成物**，不要手改。改内容请改 开发文档/ 下的源文件后重跑生成。
- docs/ 是 CR 原文的快照；源文档变了、这里没重跑，内容就会旧。
"""


def find_doc_dir(start):
    """从脚本所在目录往上找含 `开发文档/` 的目录，返回 (项目根, 文档根)。

    为什么不 import 汇总.py：那是可直接执行的脚本，import 会把整个汇总跑一遍。
    八行代码，重复比耦合安全。
    """
    d = os.path.abspath(start)
    while True:
        cand = os.path.join(d, '开发文档')
        if os.path.isdir(cand):
            return d, cand
        parent = os.path.dirname(d)
        if parent == d:
            raise SystemExit('找不到含 `开发文档/` 的项目根（从 %s 往上）' % start)
        d = parent


ROOT, DOC = find_doc_dir(HERE)
SUMDIR = os.path.join(DOC, SUM_NAME)
VENDOR = os.path.join(SUMDIR, 'vendor')
DOCS = os.path.join(SUMDIR, 'docs')


# ───────────────────────────── 同步依赖 ─────────────────────────────

def sync_vendor():
    """把 Docsify 的两个文件复制进 `_汇总/vendor/`，让目录自包含。"""
    for name in VENDOR_FILES:
        src = os.path.join(ASSETS, name)
        if not os.path.isfile(src):
            raise SystemExit('[错误] 技能资源缺失：assets/%s —— 预览依赖它，不要删' % name)
    if os.path.isdir(VENDOR):
        shutil.rmtree(VENDOR)
    os.makedirs(VENDOR)
    total = 0
    for name in VENDOR_FILES:
        shutil.copy2(os.path.join(ASSETS, name), os.path.join(VENDOR, name))
        total += os.path.getsize(os.path.join(VENDOR, name))
    return total


def _newer(src, dst):
    """dst 不存在、或 src 更新、或大小不同 ⇒ 需要复制。"""
    if not os.path.isfile(dst):
        return True
    if os.path.getsize(src) != os.path.getsize(dst):
        return True
    return os.path.getmtime(src) > os.path.getmtime(dst) + 1e-6


def sync_docs():
    """把三类 CR 的 .md 增量同步到 `_汇总/docs/`（快照）。

    为什么复制而不是引用：打包要自包含。整个 `_汇总/` 拷走后，docs/ 里的相对链接
    （如 `docs/01需求/CR-x/需求.md`）依然成立，因为目录结构原样保留。

    为什么**增量**而不是每次清空重建：70+ 个文件全删再全拷，既慢又没必要；
    清空重建还会踩到批量删除的保护（沙箱 / 杀软都可能拦）。只复制变过的，
    再单独清掉已经不存在的 CR 目录。

    返回 (总数, 本次更新数, 清理数)。
    """
    os.makedirs(DOCS, exist_ok=True)
    wanted = set()
    total = updated = 0
    for kind in KIND_DIRS:
        kdir = os.path.join(DOC, kind)
        if not os.path.isdir(kdir):
            continue
        for d in os.listdir(kdir):
            src_cr = os.path.join(kdir, d)
            if not (d.startswith('CR') and os.path.isdir(src_cr)):
                continue
            wanted.add(os.path.join(kind, d))
            for dirpath, _dirnames, filenames in os.walk(src_cr):
                rel = os.path.relpath(dirpath, src_cr)
                target_dir = os.path.join(DOCS, kind, d) if rel == '.' \
                    else os.path.join(DOCS, kind, d, rel)
                for fn in filenames:
                    if not fn.endswith('.md'):
                        continue        # 证据/ 里的截图、录屏不复制（体积大且非文档）
                    src = os.path.join(dirpath, fn)
                    dst = os.path.join(target_dir, fn)
                    total += 1
                    if _newer(src, dst):
                        os.makedirs(target_dir, exist_ok=True)
                        shutil.copy2(src, dst)
                        updated += 1

    removed = 0
    for kind in KIND_DIRS:
        kdst = os.path.join(DOCS, kind)
        if not os.path.isdir(kdst):
            continue
        for d in os.listdir(kdst):
            if os.path.join(kind, d) not in wanted:
                shutil.rmtree(os.path.join(kdst, d))
                removed += 1
    return total, updated, removed


# ─────────────────────────── 生成入口与侧边栏 ───────────────────────────

def _sort_key(dirname):
    """CR-0 < CR-1 < … < CR-16102100：按号里的数字排，不按字符串。"""
    import re
    m = re.match(r'CR[-_]?(\d+)', dirname)
    return (0, int(m.group(1))) if m else (1, 0)


def _cr_name(dirname):
    """`CR-16102100-源码拆模块` → `CR-16102100 源码拆模块`"""
    parts = dirname.split('-')
    if len(parts) >= 3:
        return '%s-%s %s' % (parts[0], parts[1], '-'.join(parts[2:]))
    return dirname


def _docs_of(cr_path):
    """一条 CR 下所有 .md（含 设计/ 子目录），按 DOC_ORDER 排。"""
    names = [f for f in os.listdir(cr_path) if f.endswith('.md')]
    design = os.path.join(cr_path, '设计')
    design_names = []
    if os.path.isdir(design):
        design_names = ['设计/' + f for f in sorted(os.listdir(design)) if f.endswith('.md')]

    def rank(n):
        base = n.split('/')[-1]
        return DOC_ORDER.index(base) if base in DOC_ORDER else 99

    return sorted(names, key=rank) + design_names


def build_sidebar():
    """侧边栏：9 个汇总视图 + 三类 CR 的文档树（全部相对路径）。"""
    out = ['- **汇总视图**']
    views = [f for f in os.listdir(SUMDIR) if f.endswith('.md') and f != '_sidebar.md']
    priority = ['状态.md', '需求索引.md', '当前需求全貌.md', '风险与资源.md',
                '技术设计.md', '决策记录.md', '项目现状.md', '运维说明.md', '审计视图.md']
    views = ([v for v in priority if v in views] + [v for v in views if v not in priority])
    for v in views:
        out.append('- [%s](%s)' % (v[:-3], v))

    for kind in KIND_DIRS:
        kdir = os.path.join(DOC, kind)
        if not os.path.isdir(kdir):
            continue
        crs = sorted([d for d in os.listdir(kdir)
                      if d.startswith('CR') and os.path.isdir(os.path.join(kdir, d))],
                     key=_sort_key)
        if not crs:
            continue
        out += ['', '- **%s（%d）**' % (KIND_LABEL[kind], len(crs))]
        for d in crs:
            docs = _docs_of(os.path.join(kdir, d))
            if not docs:
                out.append('  - %s（空）' % _cr_name(d))
                continue
            base = 'docs/%s/%s/' % (kind, d)
            main = docs[0]
            out.append('  - [%s](%s%s)' % (_cr_name(d), base, main))
            for f in docs[1:]:
                out.append('    - [%s](%s%s)' % (f[:-3].split('/')[-1], base, f))
    return '\n'.join(out) + '\n'


def generate():
    """生成 index.html / _sidebar.md / vendor / docs。返回 (视图数, 引擎字节, 副本数)。"""
    if not os.path.isdir(SUMDIR):
        raise SystemExit('[错误] 没有 `开发文档/_汇总/` —— 先跑一次 汇总.py')
    views = [f for f in os.listdir(SUMDIR) if f.endswith('.md') and f != '_sidebar.md']
    if not views:
        raise SystemExit('[错误] `_汇总/` 里没有任何视图 —— 先跑一次 汇总.py')

    proj = os.path.basename(ROOT.rstrip('\\/')) or '项目'
    html = INDEX_HTML % {
        'title': proj,
        'name_js': "'%s'" % proj.replace('\\', '\\\\').replace("'", "\\'"),
    }
    with io.open(os.path.join(SUMDIR, 'index.html'), 'w', encoding='utf-8', newline='') as f:
        f.write(html)

    vendor_bytes = sync_vendor()
    doc_total, doc_updated, doc_removed = sync_docs()

    with io.open(os.path.join(SUMDIR, '_sidebar.md'), 'w', encoding='utf-8', newline='') as f:
        f.write(build_sidebar())
    with io.open(os.path.join(SUMDIR, '如何预览.txt'), 'w', encoding='utf-8', newline='') as f:
        f.write(HOWTO)

    return len(views), vendor_bytes, doc_total, doc_updated, doc_removed


# ─────────────────────────────── 服务 ───────────────────────────────

class Quiet(http.server.SimpleHTTPRequestHandler):
    """静态服务，根目录只有 `_汇总/`（越界由标准库拦截）。"""

    def log_message(self, fmt, *args):
        pass


def lan_ip():
    """取本机内网地址（不发包，只是让系统选一张出去网卡）。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return '127.0.0.1'


def main():
    ap = argparse.ArgumentParser(description='AIDLC 文档预览（自包含，可整目录打包）')
    ap.add_argument('--host', default='127.0.0.1',
                    help='监听地址，默认 127.0.0.1（只有本机能看）；要分享用 0.0.0.0')
    ap.add_argument('--port', type=int, default=8090, help='端口，默认 8090')
    ap.add_argument('--no-serve', action='store_true', help='只生成，不起服务（打包用）')
    args = ap.parse_args()

    n_views, vendor_bytes, n_docs, n_updated, n_removed = generate()
    print('已生成自包含预览目录：开发文档/%s/' % SUM_NAME)
    print('  入口        index.html        （全是相对路径，整目录可搬走）')
    print('  侧边栏      _sidebar.md')
    print('  汇总视图    %d 个' % n_views)
    print('  渲染引擎    vendor/  %.0f KB（Docsify 本地化，不连 CDN）' % (vendor_bytes / 1024.0))
    print('  CR 原文     docs/  %d 个 md（本次更新 %d，清理 %d）' % (n_docs, n_updated, n_removed))
    print('              快照：改了源文档要重跑本脚本，包里的副本才会更新')
    print('  说明        如何预览.txt（打包给别人时，对方照它做即可）')

    if args.no_serve:
        print('\n未起服务（--no-serve）。打包：把 `开发文档/%s/` 整个拷走即可。' % SUM_NAME)
        return

    socketserver.TCPServer.allow_reuse_address = True
    handler = functools.partial(Quiet, directory=SUMDIR)
    try:
        httpd = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    except OSError as exc:
        print('\n[错误] 端口 %d 起不来：%s' % (args.port, exc))
        print('       换个端口：--port 8091；查占用：netstat -ano | findstr :%d' % args.port)
        raise SystemExit(1)

    print('\n服务已启动（Ctrl+C 停止），根目录就是 `_汇总/`：')
    print('  本机    http://127.0.0.1:%d/' % args.port)
    if args.host in ('0.0.0.0', '::'):
        print('  内网    http://%s:%d/   ← 同事用这个' % (lan_ip(), args.port))
    else:
        print('  （只监听 %s，同事访问不了；要分享用 --host 0.0.0.0）' % args.host)
    print('')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止。')
    finally:
        httpd.server_close()


if __name__ == '__main__':
    main()
