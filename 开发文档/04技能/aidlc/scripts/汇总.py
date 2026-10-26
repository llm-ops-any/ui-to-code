#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总：把分片的状态 / 需求 / 审计合成三个只读视图。

设计原则：**人只写自己的分片，全局视图由本脚本生成，且生成物不进版本库。**

生成物（本地生成、**不入库**，`.gitignore` 里排除）：
  开发文档/_汇总/状态.md       ← 扫 开发文档/<类型目录>/*/状态.md
  开发文档/_汇总/需求索引.md   ← 扫 开发文档/<类型目录>/*/需求.md（头部字段）
  开发文档/_汇总/审计视图.md    ← 合并各 CR 的 审计-<人>.md 按时间倒序

为什么不入库（2026-10-21 试点2 实测）：生成物是「扫分片算出来的」，两条并行线各自跑过汇总，
内容必然不同（各自多一行 CR、生成时间也不同）→ 入库就会在合并时三方冲突。
实测一次合并：`状态.md` 冲突 3 处、`需求索引.md` 1 处，全是纯生成物，**手工解冲突毫无意义**
（正确结果只能重算）。不入库后，冲突面只剩源代码和手写文档，而文档是一人一目录，天然不冲突。

真实来源永远是分片：`<类型目录>/CR-0X/{需求,状态}.md`（审计在 CR 目录内的 `审计-<人>.md`）。

本脚本随 AIDLC 技能分发（`<技能副本>/scripts/汇总.py`），靠「往上找 `开发文档/`」定位项目，
放在哪都能跑。用法：
  python <技能副本>/scripts/汇总.py            # 生成；无变化则静默
  python <技能副本>/scripts/汇总.py --verbose  # 生成并打印明细
  python <技能副本>/scripts/汇总.py --check    # 只检查是否过期，过期退出码 1

若生成物仍被 git 跟踪，脚本会提示 `git rm --cached`（否则并行合并照样冲突）。

退出码：0 正常；1 --check 发现过期；2 读文件出错
"""

import io
import os
import re
import sys
import glob
import subprocess
import datetime

def _find_doc_dir(start):
    """从脚本所在目录往上找含 `开发文档/` 的目录，返回 (项目根, 文档根)。
    这样脚本放在 `scripts/` 还是 `开发文档/工具/` 都能跑，不用改常量。"""
    d = os.path.abspath(start)
    while True:
        cand = os.path.join(d, '开发文档')
        if os.path.isdir(cand):
            return d, cand
        parent = os.path.dirname(d)
        if parent == d:
            raise SystemExit('找不到含 `开发文档/` 的项目根（从 %s 往上）' % start)
        d = parent

ROOT, DOC = _find_doc_dir(os.path.dirname(os.path.abspath(__file__)))

# 目录名带序号，保证编辑器里顺序稳定。改这里就能适配别的编号方案。
# 类型目录直接挂在 `开发文档/` 下（不再套一层容器目录），编号 01/02/03 定死顺序。
TYPES = ('需求', '缺陷', '技术债')
KIND_DIR = {'需求': '01需求', '缺陷': '02缺陷', '技术债': '03技术债'}

# 所有跨 CR 的视图都收口到 `开发文档/_汇总/`，整个目录 gitignore（本地生成、不入库）。
# 这样「共享单文件」不再进版本库，两人并行合并时不会冲突。
SUM_NAME = '_汇总'
SUMDIR = os.path.join(DOC, SUM_NAME)

GENERATED = {
    'status': os.path.join(SUMDIR, '状态.md'),
    'index': os.path.join(SUMDIR, '需求索引.md'),
    'design': os.path.join(SUMDIR, '技术设计.md'),
    'ops': os.path.join(SUMDIR, '运维说明.md'),
    'project': os.path.join(SUMDIR, '项目现状.md'),
    'decisions': os.path.join(SUMDIR, '决策记录.md'),
    'scope': os.path.join(SUMDIR, '当前需求全貌.md'),
    'risks': os.path.join(SUMDIR, '风险与资源.md'),
    'audit': os.path.join(SUMDIR, '审计视图.md'),
}

FIELD_RE = re.compile(r'^- ([^：:]{1,12})[：:]\s*(.*)$')
# 审计条目起始，兼容两种写法（2026-10-21 修：原先只认 `## [`，中文格式被静默丢弃 → 视图 0 条）
#   awslabs 原始：`## [2026-10-21T18:05:41+08:00] 标题`
#   本技能中文 ：`## 2026-10-21T18:05:41+08:00 · 标题`
ENTRY_RE = re.compile(r'(?m)^(?=## (?:\[|\d{4}-\d{2}-\d{2}))')
TS_RE = re.compile(r'\*\*Timestamp\*\*[：:]\s*(\S+)')
HDR_TS_RE = re.compile(
    r'^## \[?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:?\d{2})?)')


def read(path):
    with io.open(path, encoding='utf-8') as f:
        return f.read()


STAMP_RE = re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}')


def _normalize(text):
    """抹掉生成时间再比，否则每跑一次都算「有变化」，--check 永远报过期。"""
    return STAMP_RE.sub('<STAMP>', text)


def write_if_changed(path, text, verbose=False):
    """只在内容变化时写盘。返回 True 表示有变化。"""
    old = read(path) if os.path.exists(path) else None
    if old is not None and _normalize(old) == _normalize(text):
        if verbose:
            print('  无变化  %s' % os.path.relpath(path, ROOT))
        return False
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    if verbose:
        print('  已更新  %s' % os.path.relpath(path, ROOT))
    return True


def fields(path, header_only=False):
    """解析文件头部的 `- 键：值` 行。header_only 时只看第一个 `## ` 之前。"""
    text = read(path)
    if header_only:
        m = re.search(r'(?m)^## ', text)
        if m:
            text = text[:m.start()]
    out = {}
    for line in text.splitlines():
        m = FIELD_RE.match(line.strip())
        if m:
            key = m.group(1).strip()
            if key not in out:
                out[key] = m.group(2).strip()
    return out


def sort_key(dirname):
    """CR-00, CR-01…, D-01 —— 基线在前，缺陷在后。"""
    m = re.match(r'CR-(\d+)', dirname)
    if m:
        return (0, int(m.group(1)))
    m = re.match(r'D-(\d+)', dirname)
    if m:
        return (1, int(m.group(1)))
    return (2, 0)


def tracked_generated():
    """仍被 git 跟踪的生成物。非空 ⇒ 并行合并会冲突，必须 git rm --cached。"""
    rels = [os.path.relpath(p, ROOT) for p in GENERATED.values()]
    try:
        r = subprocess.run(['git', 'ls-files', '--'] + rels, cwd=ROOT, check=False,
                           capture_output=True, encoding='utf-8', errors='replace')
    except Exception:
        return []
    if r.returncode != 0:
        return []
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


# CR 分三类，各在 `开发文档/<编号><类型>/CR-...` 下。判据见 SKILL.md「三种类型怎么判」。
def collect():
    rows = []
    for kind in TYPES:
        kdir = os.path.join(DOC, KIND_DIR[kind])
        if not os.path.isdir(kdir):
            continue
        for p in sorted(glob.glob(os.path.join(kdir, 'CR-*')),
                        key=lambda x: sort_key(os.path.basename(x))):
            if not os.path.isdir(p):
                continue
            d = os.path.basename(p)
            st_path = os.path.join(p, '状态.md')
            rq_path = os.path.join(p, '需求.md')
            st = fields(st_path) if os.path.exists(st_path) else {}
            rq = fields(rq_path, header_only=True) if os.path.exists(rq_path) else {}
            if not st and not rq:
                continue
            rows.append({
                'kind': kind,
                'dir': d,
                'path': p,
                'no': st.get('编号') or rq.get('变更请求') or d.split('-')[0],
                'name': st.get('名称') or d.split('-', 2)[-1],
                'owner': st.get('负责人', '—'),
                'stage': st.get('阶段', '—'),
                'gate': st.get('门禁', '—'),
                'next': st.get('下一步', '—'),
                'left': st.get('遗留', '—'),
                'unit': st.get('单元', '—'),
                'summary': rq.get('摘要', '—'),
                'seg': rq.get('号段', '—'),
                # 需求性质：基线（第一版 / v1.0）或 增量（基线之后追加的改动）。
                # 缺省按「增量」——基线是少数，只有它需要显式标注。
                'nature': rq.get('需求性质', '增量') if os.path.exists(rq_path) else '—',
                'has_req': os.path.exists(rq_path),
            })
    return rows


STAGE_LABEL = {
    'delivered': '已交付',
    'in-progress': '进行中',
    'awaiting-approval': '待批',
    'blocked': '阻塞',
    'fixed': '已修复',
    'not-started': '未开始',
    'cancelled': '已撤回',
}


def render_status(rows, stamp):
    live = [r for r in rows if r['stage'] not in ('delivered', 'fixed', 'cancelled')]
    todo = [r for r in rows if r['next'] not in ('无', '—', '')]

    out = ['# 状态（自动生成）', '',
           '> 本文件由 `scripts/汇总.py` 生成，**不要手改** —— 手改会在下次生成时被覆盖。',
           '> 要改进度：改 `<类型目录>/CR-0X-<简称>/状态.md`；项目级事实见各 CR 的 `变更说明.md`。',
           '> 生成时间：%s' % stamp, '',
           '## 一览', '']
    for kind in TYPES:
        group = [r for r in rows if r['kind'] == kind]
        if not group:
            continue
        out += ['### %s（%d）' % (kind, len(group)), '',
                '| 编号 | 名称 | 负责人 | 阶段 | 下一步 |',
                '|---|---|---|---|---|']
        for r in group:
            stage = STAGE_LABEL.get(r['stage'], r['stage'])
            out.append('| **%s** | %s | %s | %s | %s |' % (r['no'], r['name'], r['owner'], stage, r['next']))
        out.append('')
    out += ['', '## 汇总', '',
            '- 共 **%d** 条线（%s）：%s' % (len(rows),
                '、'.join('%s %d' % (k, sum(1 for r in rows if r['kind'] == k))
                         for k in TYPES if any(x['kind'] == k for x in rows)),
                '、'.join(
                '%s %d' % (STAGE_LABEL.get(k, k), sum(1 for r in rows if r['stage'] == k))
                for k in ('delivered', 'fixed', 'in-progress', 'awaiting-approval', 'blocked', 'cancelled')
                if any(r['stage'] == k for r in rows))),
            '- 进行中：%s' % ('、'.join('%s %s' % (r['no'], r['name']) for r in live) if live else '**无**'),
            '- 待人工处理：**%d** 条（见上表「下一步」列）' % len(todo), '']

    out += ['## 门禁明细', '']
    for r in rows:
        out.append('- **%s %s**：%s' % (r['no'], r['name'], r['gate']))
    left = [r for r in rows if r['left'] not in ('无', '—', '')]
    out += ['', '## 遗留', '']
    if left:
        for r in left:
            out.append('- **%s %s**：%s' % (r['no'], r['name'], r['left']))
    else:
        out.append('- 无')
    out += ['', '---', '',
            '项目级事实（部署、存储、扩展开关、身份）见 `项目现状.md`；'
            'CR 怎么找见 `_汇总/需求索引.md`。', '']
    return '\n'.join(out)


SEG_RE = re.compile(r'^([A-Z]+)-(?:(\d+[a-z]?)[~-]([A-Z]+-)?(\d+[a-z]?)|(\d+[a-z]?))$')


def parse_segments(seg):
    items = []
    for token in re.split(r'[、,，]\s*', seg.strip()):
        token = token.strip()
        if not token or token == '—':
            continue
        m = SEG_RE.match(token.replace(' ', ''))
        if not m:
            # 容错：号段字段常被写成 `AC-01~AC-04（CR 内编号）` 这类带说明的形式。
            # 能捞出 `X-数字` 就用，捞不出就跳过 —— **不能因为一行格式不规整就让整个汇总崩掉**。
            m2 = re.search(r'(N?FR|AC|S|A)-?(\d+)', token, re.I)
            if m2:
                items.append((m2.group(1).upper(), m2.group(2), m2.group(2)))
            continue
        prefix = m.group(1)
        if m.group(5):
            items.append((prefix, m.group(5), m.group(5)))
        else:
            items.append((prefix, m.group(2), m.group(4)))
    def _num(v):
        mm = re.match(r'(\d+)', str(v or ''))
        return int(mm.group(1)) if mm else 9999
    items.sort(key=lambda x: ({'FR': 0, 'NFR': 1, 'AC': 2, 'S': 3, 'A': 4}.get(x[0], 9), _num(x[1])))
    return items


def render_index(rows, stamp):
    out = ['# 需求索引（自动生成）', '',
           '> 由 `scripts/汇总.py` 生成，**不要手改**。改需求请改各 `CR-0X/需求.md` 的头部字段。',
           '> 生成时间：%s' % stamp, '',
           '## 一、CR 一览', '']
    for kind in TYPES:
        group = [r for r in rows if r['kind'] == kind]
        if not group:
            continue
        out += ['### %s（%d）' % (kind, len(group)), '',
                '| 目录 | 编号 | 性质 | 摘要 | 号段 | 阶段 |',
                '|---|---|---|---|---|---|']
        for r in group:
            nature = '**基线**' if r['nature'] == '基线' else r['nature']
            out.append('| `%s/%s/` | **%s** | %s | %s | %s | %s |' % (
                KIND_DIR[kind], r['dir'], r['no'], nature, r['summary'], r['seg'],
                STAGE_LABEL.get(r['stage'], r['stage'])))
        out.append('')

    out += ['', '## 二、ID 号段 → 文件', '',
            '路径相对 `开发文档/`（类型目录 `01需求` / `02缺陷` / `03技术债`）。', '',
            '| ID | 号段 | 文件 |', '|---|---|---|']
    for r in rows:
        for prefix, lo, hi in parse_segments(r['seg']):
            span = '%s-%s' % (prefix, lo) if lo == hi else '%s-%s ~ %s-%s' % (prefix, lo, prefix, hi)
            out.append('| %s | %s | `%s/%s` |' % (prefix, span, KIND_DIR[r['kind']] + '/' + r['dir'],
                                                  '需求.md' if r['has_req'] else '状态.md'))

    out += ['', '## 三、新增一个需求的步骤', '',
            '1. **算号**：`P + Y + MMDD + N` 共 8 位 —— 人编号 1 位（见 `00规则/团队配置.md`）、'
            '年末位 1 位、月日 2 位、当天第几个 2 位（**从 00 起**）。例 `16102100` = 人1 / 2026 / 10-21 / 当天第 00 个。',
            '2. **建目录**：`CR-<8位号>-<中文简称>/`（**目录名就是号，不需要号段文件**），例 `CR-16102100-导出CSV/`；'
            '   里面至少放一个 `状态.md`（阶段可写 `not-started` = 占了号还没开工）。'
            '   首位是人 ⇒ 两人永不撞；一天最多 100 个（00~99）。',
            '3. **写 `需求.md`**，头部必须有这几个字段（索引和全貌靠它生成）：',
            '   `- 需求性质：增量`（基线写 `基线`，全项目仅一条）、`- 变更请求：CR-16102100`、'
            '`- 摘要：一句话`、`- 号段：FR-01~FR-03、AC-01~AC-02`（**CR 内编号**，'
            '跨 CR 引用写 `CR-16102100/FR-01`，不复制正文）。',
            '4. **写 `状态.md`**，字段：`编号/名称/负责人/阶段/门禁/下一步/单元/遗留`。',
            '5. 按需加 `设计.md` / `测试记录.md` / `验收报告.md` / `问题.md`，**不建空文件**。',
            '6. 跑一次 `python <技能副本>/scripts/汇总.py` 刷新本索引。', '',
            '> **唯一标识一律用 `CR-<8位号>`**（目录名就是号）。不要另造 `R7`、`CR-2` 之类的短号 —— 两套号并存，迟早对不上。', '']
    return '\n'.join(out)


def _rel(p):
    return os.path.relpath(p, DOC).replace(os.sep, '/')


def _demote(body, levels=1):
    """把分片正文里的标题降级：`## 一、xxx` → `### 一、xxx`（levels=2 时连降两级）。

    否则分片的 `##` 会和视图自己的节标题平级，目录结构就乱了。
    `当前需求全貌.md` 的每条 CR 已经是 `##`，正文要降两级才挂得住。
    """
    for _ in range(levels):
        body = re.sub(r'(?m)^(#{1,5}) ', r'#\1 ', body)
    return body


def _body_of(text, levels=1):
    """去掉分片自己的 H1（视图已经有节标题了），其余标题降 `levels` 级。"""
    lines = text.strip().splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].startswith('# '):
        lines = lines[1:]
    return _demote('\n'.join(lines).strip(), levels)


def _sec(no, title, body, src):
    return ['## %s / %s' % (no, title), '', _body_of(body), '', '> 来源：`%s`' % _rel(src), '', '---', '']


def render_design(rows, stamp):
    """技术设计 = 各 CR 的 `设计/*.md` 按 CR 顺序拼接。真正的设计在各自 CR 目录里。"""
    entries = []
    for r in rows:
        ddir = os.path.join(r['path'], '设计')
        if not os.path.isdir(ddir):
            continue
        for fn in sorted(f for f in os.listdir(ddir) if f.endswith('.md')):
            p = os.path.join(ddir, fn)
            entries.append((r['no'], os.path.splitext(fn)[0], read(p).strip(), p))
    out = ['# 技术设计（自动生成）', '',
           '> 由 `scripts/汇总.py` 合并各 CR 的 `设计/*.md`，按 CR 号顺序，**不要手改**。',
           '> 真正的设计在 `<类型目录>/CR-XXXX/设计/` 下 —— 每条 CR 只写自己那份，互不冲突。',
           '> 生成时间：%s ｜ 共 **%d** 节' % (stamp, len(entries)), '', '---', '']
    for no, title, body, src in entries:
        out += _sec(no, title, body, src)
    if not entries:
        out.append('_（还没有任何 CR 写设计增量）_')
    return '\n'.join(out)


def render_ops(rows, stamp):
    """运维说明 = 各 CR 的 `运维说明.md`（只有部署类 CR 才有）。"""
    entries = []
    for r in rows:
        p = os.path.join(r['path'], '运维说明.md')
        if os.path.isfile(p):
            entries.append((r['no'], read(p).strip(), p))
    out = ['# 运维说明（自动生成）', '',
           '> 由 `scripts/汇总.py` 合并各 CR 的 `运维说明.md`，**不要手改**。',
           '> 只有部署 / 上线类 CR 才有这一份；平时在各自 `CR-XXXX/运维说明.md` 里写。',
           '> 生成时间：%s ｜ 共 **%d** 条' % (stamp, len(entries)), '', '---', '']
    for no, body, src in entries:
        out += ['## %s' % no, '', _body_of(body), '', '> 来源：`%s`' % _rel(src), '', '---', '']
    if not entries:
        out.append('_（本项目还没有部署类 CR）_')
    return '\n'.join(out)


def render_project(rows, stamp):
    """项目现状 = 各 CR 的 `变更说明.md`（对项目级事实的影响）。

    身份 / 审批模式 / 测试策略 / 团队这类**不随 CR 变**的东西留在 `00规则/团队配置.md`，不进本文件。
    """
    entries = []
    for r in rows:
        p = os.path.join(r['path'], '变更说明.md')
        if os.path.isfile(p):
            entries.append((r['no'], read(p).strip(), p))
    out = ['# 项目现状（自动生成）', '',
           '> 由 `scripts/汇总.py` 合并各 CR 的 `变更说明.md`，**不要手改**。',
           '> 项目级配置（身份 / 审批模式 / 测试策略 / 团队）见 `00规则/团队配置.md`。',
           '> 生成时间：%s ｜ 共 **%d** 条变更' % (stamp, len(entries)), '', '---', '']
    for no, body, src in entries:
        out += ['## %s' % no, '', _body_of(body), '', '> 来源：`%s`' % _rel(src), '', '---', '']
    if not entries:
        out.append('_（还没有任何 CR 写变更说明）_')
    return '\n'.join(out)


def render_decisions(rows, stamp):
    """跨 CR 的决策台账：整个项目做过哪些技术取舍、为什么、谁定的。

    单条 CR 的决策在 `CR-XXXX/决策记录.md`；这份是给人回顾用的索引（交付汇报、交接、复盘）。
    """
    entries = []
    for r in rows:
        p = os.path.join(r['path'], '决策记录.md')
        if os.path.isfile(p):
            entries.append((r['no'], read(p).strip(), p))
    out = ['# 决策记录（自动生成）', '',
           '> 由 `scripts/汇总.py` 合并各 CR 的 `决策记录.md`，**不要手改**。',
           '> 这里记「为什么这么做」：选型对比、被否掉的方案、决策人和时间。',
           '> **项目复盘 / 交接时先看这份** —— 它比代码更能说明当初的边界在哪。',
           '> 生成时间：%s ｜ 共 **%d** 条 CR 有决策' % (stamp, len(entries)), '', '---', '']
    for no, body, src in entries:
        out += ['## %s' % no, '', _body_of(body), '', '> 来源：`%s`' % _rel(src), '', '---', '']
    if not entries:
        out.append('_（还没有任何 CR 写决策记录）_')
    return '\n'.join(out)


def render_scope(rows, stamp):
    """当前需求全貌：基线 + 各增量 CR 的需求正文，按演进顺序拼成一份。

    单条 CR 只回答「这次改了什么」。想知道「系统现在一共要满足什么」，得把基线和
    各增量拼起来读 —— 这个视图就是拼好的结果，**不手写、不入库**。
    """
    base = [r for r in rows if r['nature'] == '基线']
    incr = sorted([r for r in rows if r['nature'] == '增量'], key=lambda r: sort_key(r['dir']))
    defects = [r for r in rows if r['nature'] == '—']
    ordered = base + incr

    out = ['# 当前需求全貌（自动生成）', '',
           '> 由 `scripts/汇总.py` 合成：**基线需求 + 各增量 CR 的需求正文**，按编号（约等于时间）排序。',
           '> **不要手改** —— 改对应 CR 的 `需求.md` 后重跑脚本即可。',
           '> 想知道「这个系统现在一共要满足什么」，看这一份就够，不用逐个翻 CR 目录。',
           '> 生成时间：%s ｜ 基线 **%d** 条 · 增量 **%d** 条' % (stamp, len(base), len(incr)), '',
           '## 一、清单', '']

    if not ordered:
        out.append('_（还没有任何 CR 写需求文档）_')
        return '\n'.join(out)

    out += ['| 性质 | 编号 | 名称 | 摘要 | FR/AC 号段 |',
            '|---|---|---|---|---|']
    for r in ordered:
        nature = '**基线**' if r['nature'] == '基线' else '增量'
        out.append('| %s | **%s** | %s | %s | %s |' % (
            nature, r['no'], r['name'], r['summary'], r['seg']))
    out.append('')

    out += ['## 二、正文', '',
            '> 顺序：基线在前，增量按编号（≈时间）升序。每节都标了来源 CR。', '']
    for r in ordered:
        rq = os.path.join(r['path'], '需求.md')
        tag = '基线' if r['nature'] == '基线' else '增量'
        out += ['## %s · %s %s' % (tag, r['no'], r['name']), '',
                _body_of(read(rq), levels=2), '',
                '> 来源：`%s`' % _rel(rq), '', '---', '']

    if defects:
        out += ['> 另有 **%d** 条缺陷 CR 不在本视图：缺陷记的是「与已批准预期不符」，不是需求。'
                % len(defects),
                '> 见 `%s`。' % _rel(GENERATED['index']), '']
    return '\n'.join(out)


# 风险/资源的排序权重：数字越小越该先看
_LV = {'高': 0, '中': 1, '低': 2, '—': 3, '': 3}
_ST = {'待处理': 0, '已发生': 0, '已缓解': 1, '已接受': 2, '已关闭': 3, '': 2}
_RS = {'待提供': 0, '可替代': 1, '已有': 2, '不适用': 3, '': 3}


def _md_table(text):
    """取 markdown 里的**第一张表**，返回 [{表头: 单元格}]。

    只取第一张：这两份文件的约定就是「先一张表，后面随便写说明」，
    多表混解析会让列名对不上（比如两张表都有「状态」）。
    """
    head = None
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('|') and s.endswith('|'):
            cells = [c.strip() for c in s[1:-1].split('|')]
            if head is None:
                head = cells
                continue
            if cells and all(set(c) <= set('-: ') for c in cells):
                continue                      # 分隔行 |---|---|
            out.append(dict(zip(head, cells)))
        elif out:
            break                             # 第一张表结束
    return out


def _base(v):
    """去掉括号说明：`已接受（成本>收益）` → `已接受`。

    状态列允许带理由（这是好事），但排序和统计只认前半段。
    """
    return re.split(r'[（(]', (v or '').strip(), maxsplit=1)[0].strip()


def _get(row, key):
    """按表头**前缀**取值：表头常写成「触发信号（怎么知道它发生了）」这种带说明的形式。

    精确匹配会取不到，整列变成「—」，而「—」看起来像"没有这个风险"，比报错更难发现。
    """
    if key in row:
        return row[key]
    for k, v in row.items():
        if k.startswith(key):
            return v
    return '—'


def render_risks(rows, stamp):
    """风险台账 + 前置资源清单，合成一份「开工前 / 交付前」的检查单。

    为什么要有这份：风险写在各自 CR 的 `风险.md` 里，看单条 CR 时很清楚，
    但「这个项目现在卡在哪、哪儿可能炸」必须跨 CR 汇总才看得出来。
    """
    risks, res = [], []
    for r in rows:
        rp = os.path.join(r['path'], '风险.md')
        if os.path.isfile(rp):
            for it in _md_table(read(rp)):
                if _get(it, '风险') == '—':
                    continue
                risks.append({
                    'cr': r['no'], 'name': r['name'], 'kind': r['kind'],
                    'id': _get(it, '编号'), 'risk': _get(it, '风险'),
                    'p': _get(it, '可能性'), 'i': _get(it, '影响'),
                    'sig': _get(it, '触发信号'), 'act': _get(it, '应对'),
                    'st': _get(it, '状态'),
                })
        rp2 = os.path.join(r['path'], '前置资源.md')
        if os.path.isfile(rp2):
            for it in _md_table(read(rp2)):
                if _get(it, '资源') == '—':
                    continue
                res.append({
                    'cr': r['no'], 'name': r['name'],
                    'res': _get(it, '资源'), 'type': _get(it, '类型'),
                    'need': _get(it, '必需性'), 'st': _get(it, '状态'),
                    'who': _get(it, '谁提供'),
                    'alt': _get(it, '替代方案'),
                })

    # 状态列允许带理由（`已接受（成本 > 收益）`），排序与统计只认前半段
    for x in risks:
        x['stk'] = _base(x['st'])
    for x in res:
        x['stk'] = _base(x['st'])

    active = [x for x in risks if x['stk'] in ('待处理', '已发生', '—', '')]
    high = [x for x in active if x['i'] == '高']
    pending = [x for x in res if x['stk'] == '待提供']
    pending_need = [x for x in pending if x['need'] == '必需']

    out = ['# 风险与前置资源（自动生成）', '',
           '> 由 `scripts/汇总.py` 合并各 CR 的 `风险.md` 与 `前置资源.md`，**不要手改**。',
           '> **开工前看第一节**（资源没到位就别开工）；**交付前看第二节**（高风险是否都已处理）。',
           '> 生成时间：%s' % stamp, '',
           '**活跃风险 %d 条**（其中高影响 **%d** 条）｜**资源待提供 %d 项**（其中必需 **%d** 项）'
           % (len(active), len(high), len(pending), len(pending_need)), '', '---', '']

    # 一、资源
    out += ['## 一、前置资源（待提供在最前）', '']
    if not res:
        out.append('_（还没有任何 CR 写 `前置资源.md`）_')
    else:
        out += ['| CR | 资源 | 类型 | 必需性 | 状态 | 谁提供 / 在哪 | 替代方案 |',
                '|---|---|---|---|---|---|---|']
        for x in sorted(res, key=lambda y: (_RS.get(y['stk'], 3),
                                           0 if y['need'] == '必需' else 1, y['cr'])):
            mark = '**%s**' % x['res'] if x['st'] == '待提供' else x['res']
            out.append('| %s %s | %s | %s | %s | %s | %s | %s |' % (
                x['cr'], x['name'], mark, x['type'], x['need'], x['st'], x['who'], x['alt']))
    out += ['', '---', '']

    # 二、风险
    out += ['## 二、风险台账（影响 × 可能性，活跃的在前）', '']
    if not risks:
        out.append('_（还没有任何 CR 写 `风险.md`）_')
    else:
        out += ['| CR | 编号 | 风险 | 可能性 | 影响 | 触发信号 | 应对 | 状态 |',
                '|---|---|---|---|---|---|---|---|']
        for x in sorted(risks, key=lambda y: (_ST.get(y['stk'], 2), _LV.get(y['i'], 3),
                                             _LV.get(y['p'], 3), y['cr'])):
            out.append('| %s | %s | %s | %s | %s | %s | %s | %s |' % (
                x['cr'], x['id'], x['risk'], x['p'], x['i'], x['sig'], x['act'], x['st']))

    if risks or res:
        out += ['', '> 数据来源：`01需求|02缺陷|03技术债/CR-*/{风险,前置资源}.md`。',
                '> 新增或改状态后重跑 `汇总.py`；本视图不入库。']
    return '\n'.join(out)


def render_audit(stamp):
    entries = []
    # 审计跟着 CR 走：`<类型目录>/CR-*/审计-<人>.md`（一人一份，追加式，天然不冲突）
    paths = []
    for kind in TYPES:
        paths += sorted(glob.glob(os.path.join(DOC, KIND_DIR[kind], 'CR-*', '审计-*.md')))
    for path in paths:
        if os.path.basename(path) == '视图.md':
            continue
        text = read(path)
        src = os.path.relpath(path, DOC).replace(os.sep, '/')
        for chunk in ENTRY_RE.split(text):
            chunk = chunk.strip()
            if not chunk.startswith('## '):
                continue
            h = HDR_TS_RE.match(chunk)
            m = TS_RE.search(chunk)
            ts = h.group(1) if h else (m.group(1) if m else '')
            entries.append((ts, src, chunk.rstrip()))

    entries.sort(key=lambda x: x[0], reverse=True)

    out = ['# 审计视图（自动生成）', '',
           '> 由 `scripts/汇总.py` 合并 `CR-*/审计-<人>.md` 生成，**按时间倒序**，**不要手改**。',
           '> 原始条目在各 CR 的 `审计-<人>.md`，一人一份、只追加；本文件只读不写回。',
           '> 生成时间：%s ｜ 共 **%d** 条' % (stamp, len(entries)), '', '---', '']
    for ts, src, body in entries:
        out.append(body)
        out.append('')
        out.append('> 来源：`%s`' % src)
        out.append('')
        out.append('---')
        out.append('')
    return '\n'.join(out)


def main():
    argv = sys.argv[1:]
    verbose = '--verbose' in argv or '-v' in argv
    check_only = '--check' in argv

    if not os.path.isdir(DOC):
        print('找不到 %s' % DOC)
        return 2

    rows = collect()
    if not rows:
        print('没有可汇总的 CR（找不到 %s 下的 CR-*/状态.md）' % ' / '.join(KIND_DIR.values()))
        print('  期望布局：开发文档/<类型目录>/CR-XXXX-<简称>/{需求.md,状态.md}')
        print('  还没建需求目录时属正常；先按技能第 E 节的编号目录建出来。')
        return 2

    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    targets = {
        GENERATED['status']: render_status(rows, stamp),
        GENERATED['index']: render_index(rows, stamp),
        GENERATED['design']: render_design(rows, stamp),
        GENERATED['ops']: render_ops(rows, stamp),
        GENERATED['project']: render_project(rows, stamp),
        GENERATED['decisions']: render_decisions(rows, stamp),
        GENERATED['scope']: render_scope(rows, stamp),
        GENERATED['risks']: render_risks(rows, stamp),
        GENERATED['audit']: render_audit(stamp),
    }
    if not check_only:
        try:
            os.makedirs(SUMDIR, exist_ok=True)
        except OSError:
            pass

    changed = []
    for path, text in targets.items():
        old = read(path) if os.path.exists(path) else None
        if old is not None and _normalize(old) == _normalize(text):
            if verbose:
                print('  无变化  %s' % os.path.relpath(path, ROOT))
            continue
        changed.append(path)
        if not check_only:
            write_if_changed(path, text, verbose)

    if check_only:
        if changed:
            print('生成物已过期：')
            for p in changed:
                print('  %s' % os.path.relpath(p, ROOT))
            print('\n跑一次 `python <技能副本>/scripts/汇总.py` 重新生成。')
            return 1
        print('生成物是最新的。')
        return 0

    if not changed:
        if verbose:
            print('全部最新，无需改动。')
        return 0

    print('已在本地生成 %d 个视图（**不入库**，别提交）：' % len(changed))
    for p in changed:
        print('  %s' % os.path.relpath(p, ROOT))

    stuck = tracked_generated()
    if stuck:
        print('')
        print('⚠ 这些生成物仍被 git 跟踪 —— 不处理的话，两人并行合并照样冲突：')
        for p in stuck:
            print('  %s' % p)
        print('  一次性移除：git rm --cached --%s' % ''.join(' "%s"' % p for p in stuck))
        print('  再跑一次 安装钩子.py，会把它们补进 .gitignore')
    return 0


if __name__ == '__main__':
    sys.exit(main())
