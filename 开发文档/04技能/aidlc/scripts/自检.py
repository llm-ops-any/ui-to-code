#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIDLC 项目自检（doctor）—— 「技能说的话，项目做到了没有？」

为什么要它：技能的规则写在 SKILL.md 里，但**规则不会自己执行**。2026-10-21 一天里踩到两个
同类问题（技能副本落到项目根 `skills/`、装钩子不写 `.gitattributes`），共同点是「本机能跑、
换台机器就静默失效，而且没有任何报错」。这类问题只能靠**主动体检**发现，靠人记住是不行的。

检查 13 类（✓ 通过 / · 不适用或未建 / ⚠ 建议处理 / ✗ 有问题）：

  1. 锚点          AGENTS.md 等有没有 AIDLC 标记段 —— 没有 ⇒ 技能根本不会被触发
  2. 技能副本      在 `开发文档/04技能/aidlc`（固定落点）；项目根有没有多余的 `skills/`
  3. 钩子          `core.hooksPath` 指向对不对；三个钩子在不在；首行是不是 LF
  4. .gitattributes LF 保护三行齐不齐 —— 缺了换机器 clone 后钩子静默失效
  5. 布局          五个编号目录齐不齐
  6. 生成物        `_汇总/` 下 9 个视图在不在；`汇总.py --check` 是不是最新
  7. 编号          CR 号有没有重复（并行时撞号的直接证据）
  8. 基线          `需求性质：基线` 有且仅有一条 —— 否则全貌视图分不清基线和增量
  9. 前置资源      必需资源「待提供」却已开工 ⇒ 判错
 10. 风险          高影响风险仍「待处理」而 CR 在做 ⇒ 建议确认
 11. 死规则        脚本解析的字段若全项目 0 使用 ⇒ 解析永远空转，报警
 12. 孤儿 CR       CR 目录缺 状态.md/需求.md/问题.md ⇒ 汇总会**静默跳过**它
 14. 规则文件      团队配置.md 是不是「整份复制 + 填空」：档位名、五档清单、含义表、测试三档

用法
    python 开发文档/04技能/aidlc/scripts/自检.py          # 体检
    python 开发文档/04技能/aidlc/scripts/自检.py --fix     # 只修能安全自动修的（补 .gitattributes）
    python 开发文档/04技能/aidlc/scripts/自检.py --quiet   # 只报问题（✓ 不打印）
    python 开发文档/04技能/aidlc/scripts/自检.py --status  # 同体检，退出码用于钩子/CI

退出码：0 全绿｜1 有 ✗（真问题）｜2 只有 ⚠（能用，但建议处理）
"""

import glob
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# 不生成 __pycache__：技能副本是只读资源，在里面写字节码会污染项目（git 还会看见）
sys.dont_write_bytecode = True

sys.path.insert(0, HERE)
from _aidlc_common import (GITATTR_HEAD, GITATTR_LINES,  # noqa: E402
                           gitattributes_missing)
MARK = 'AIDLC:v2 BEGIN'
LAYOUT = ('00规则', '01需求', '02缺陷', '03技术债', '04技能')
REQUIRED_DIRS = ('00规则', '01需求', '02缺陷', '03技术债')
SUMDIR = '开发文档/_汇总'
GENERATED = (
    SUMDIR + '/状态.md',
    SUMDIR + '/需求索引.md',
    SUMDIR + '/技术设计.md',
    SUMDIR + '/运维说明.md',
    SUMDIR + '/项目现状.md',
    SUMDIR + '/决策记录.md',
    SUMDIR + '/当前需求全貌.md',
    SUMDIR + '/风险与资源.md',
    SUMDIR + '/审计视图.md',
)
CR_RE = re.compile(r'CR[-_]?(\d+)')
DECL_RE = re.compile(r'^[-*]\s*CR[：:]\s*CR[-_]?(\d+)', re.M)

try:                       # GBK 控制台下打印 ✓ 会抛 UnicodeEncodeError（试点1 踩过）
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def find_root(start):
    """找项目根：先问 git，再退回「往上找含 开发文档/ 的目录」，都没有返回 None。

    `encoding='utf-8'` 不能省：Windows 下 `text=True` 走 locale(cp936)，git 输出的
    UTF-8 中文路径会变乱码，交给 `cwd=` 就是 WinError 267。"""
    r = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=start,
                       capture_output=True, encoding='utf-8', errors='replace')
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    d = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(d, '开发文档')):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


# 先看「我在哪」，再看「脚本在哪」—— 脚本可能被从宿主技能目录直接调用，
# 那时若按脚本位置算，会去体检技能自己（2026-10-21 实测踩到）。
ROOT = find_root(os.getcwd()) or find_root(HERE)
if not ROOT:
    print('不在任何 AIDLC 项目里：从 %s 往上没找到 开发文档/，也不在 git 仓库内。' % os.getcwd())
    print('用法：cd <项目根> 再跑本脚本。')
    sys.exit(2)
SELF = os.path.basename(os.path.abspath(__file__))


def git(*args):
    return subprocess.run(['git'] + list(args), cwd=ROOT,
                          capture_output=True, encoding='utf-8', errors='replace')


def read(path):
    try:
        with io.open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    except (IOError, OSError):
        return None


def is_repo():
    return git('rev-parse', '--is-inside-work-tree').stdout.strip() == 'true'


# ── 检查项 ────────────────────────────────────────────────────────────────
def check_anchors(rows):
    # 先看各平台 —— 有的项目刻意不让 AGENTS.md 接管（比如上游仓库自有 AGENTS.md，
    # 只允许写 CLAUDE.md）。那种情况不是错，但要说清楚「入口在哪」。
    platforms = (
        ('CLAUDE.md', 'Claude Code'),
        ('.cursor/rules/aidlc.mdc', 'Cursor'),
        ('.windsurf/rules/aidlc.md', 'Windsurf'),
        ('.github/copilot-instructions.md', 'Copilot'),
        ('.trae/rules/aidlc.md', 'Trae'),
        ('.codebuddy/rules/aidlc.mdc', 'CodeBuddy'),
        ('.workbuddy/memory/MEMORY.md', 'WorkBuddy'),
    )
    marked = []
    for rel, why in platforms:
        t = read(os.path.join(ROOT, rel))
        if t is None:
            rows.append(('d', '锚点', '%s 无（未用 %s）' % (rel, why), ''))
        elif MARK not in t:
            rows.append(('w', '锚点', '%s 存在但没有标记段' % rel, '重跑 install-project-anchors.py'))
        else:
            marked.append(rel)
            rows.append(('v', '锚点', '%s 含标记段' % rel, ''))

    p = os.path.join(ROOT, 'AGENTS.md')
    txt = read(p)
    alt = '、'.join(marked) or '其它平台'
    if txt is None:
        if marked:
            rows.append(('w', '锚点', 'AGENTS.md 不存在（入口走 %s）' % alt,
                         '本项目的入口不在 AGENTS.md；要它接管就再跑 --platforms agents'))
        else:
            rows.append(('x', '锚点', 'AGENTS.md 不存在，且没有任何平台入口',
                         '跑 install-project-anchors.py <项目根> —— 没有锚点，技能不会被触发'))
    elif MARK not in txt:
        if marked:
            rows.append(('w', '锚点', 'AGENTS.md 没有标记段（入口走 %s）' % alt,
                         '刻意不接管 AGENTS.md 的话可以忽略；否则跑 --platforms agents 补上'))
        else:
            rows.append(('x', '锚点', 'AGENTS.md 没有 AIDLC 标记段',
                         '重跑 install-project-anchors.py，它会整段补齐（不动你原有内容）'))
    else:
        rows.append(('v', '锚点', 'AGENTS.md 含 AIDLC:v2 段', ''))


# 技能副本固定落点。测试阶段不做旧落点兼容（兼容分支是死代码）。
SKILL_REL = '开发文档/04技能/aidlc'


def check_skill_copy(rows):
    main = os.path.join(ROOT, SKILL_REL)
    if os.path.isfile(os.path.join(main, 'SKILL.md')):
        n = sum(1 for d, _dn, fs in os.walk(main) for _f in fs if '__pycache__' not in d)
        rows.append(('v', '技能副本', '%s/（%d 个文件）' % (SKILL_REL, n), ''))
    else:
        rows.append(('x', '技能副本', '找不到 %s/SKILL.md' % SKILL_REL,
                     '跑 install-project-anchors.py <项目根> --with-skill，项目才能自包含'))

    root_skills = os.path.join(ROOT, 'skills')
    if os.path.isdir(root_skills):
        # 只有「把 aidlc 放错位置」才算错。项目自带 skills/（agent 技能仓库、OPC 的 paperclip
        # 技能包）是正常内容，不能一概判错 —— 2026-10-26 opcapp 实测误报。
        misplaced = (os.path.isfile(os.path.join(root_skills, 'aidlc', 'SKILL.md'))
                     or os.path.isfile(os.path.join(root_skills, 'SKILL.md')))
        if misplaced:
            rows.append(('x', '技能副本', '项目根 skills/ 里放的是 aidlc 副本',
                         '项目根不放技能副本，只放 %s/' % SKILL_REL))
        else:
            rows.append(('d', '技能副本', '项目根 skills/ 是项目自己的（不含 aidlc），不影响', ''))
    pyc = [d for d, _dn, _fn in os.walk(main) if os.path.basename(d) == '__pycache__']
    if pyc:
        rows.append(('w', '技能副本', '技能副本里有 __pycache__',
                     '会让副本与技能源 diff 出差异；删掉（别提交）'))


def proj_skill():
    """项目自带的技能副本目录；没有就返回 None。
    注意：**不能退回脚本自己所在的 HOST 技能目录** —— 那样会拿宿主技能自带的钩子
    去给项目打绿勾，等于自欺（2026-10-21 实测踩到）。"""
    cand = os.path.join(ROOT, SKILL_REL)
    return cand if os.path.isdir(cand) else None


def check_hooks(rows):
    if not is_repo():
        rows.append(('d', '钩子', '不是 git 仓库，跳过', '需要自动汇总时再 git init'))
        return
    sk = proj_skill()
    if not sk:
        rows.append(('x', '钩子', '项目里没有技能副本，钩子无从检查',
                     '跑 install-project-anchors.py <项目根> --with-skill'))
        return
    hdir = os.path.join(sk, 'scripts', 'hooks')
    rel = os.path.relpath(hdir, ROOT).replace(os.sep, '/')

    cur = git('config', '--local', '--get', 'core.hooksPath').stdout.strip()
    if not cur:
        rows.append(('x', '钩子', 'core.hooksPath 未设置（合并后不会自动汇总）',
                     '跑 %s/scripts/安装钩子.py' % rel.rsplit('/scripts/', 1)[0]))
    elif cur.replace('\\', '/').rstrip('/') != rel:
        rows.append(('w', '钩子', 'core.hooksPath = %s（期望 %s）' % (cur, rel),
                     '重跑 安装钩子.py'))
    else:
        rows.append(('v', '钩子', 'core.hooksPath = %s' % rel, ''))

    bad = 0
    for h in ('post-merge', 'post-commit', 'post-rewrite', '_summary.sh'):
        p = os.path.join(hdir, h)
        if not os.path.isfile(p):
            rows.append(('x', '钩子', '缺 %s' % h, '技能副本不完整，重新同步副本'))
            bad += 1
            continue
        with open(p, 'rb') as f:
            first = f.readline()
        if b'\r' in first:
            rows.append(('x', '钩子', '%s 首行是 CRLF（shebang 带 \\r，静默不执行）' % h,
                         '补 .gitattributes 后重新 checkout；或转成 LF'))
            bad += 1
        elif h != '_summary.sh' and not first.startswith(b'#!'):
            rows.append(('w', '钩子', '%s 首行不是 shebang' % h, '检查文件是否被改坏'))
            bad += 1
    if not bad:
        rows.append(('v', '钩子', '四个钩子文件齐全且首行为 LF（merge / commit / rebase 三路径都在）', ''))


def check_gitattributes(rows, fix):
    path = os.path.join(ROOT, '.gitattributes')
    hint = '跑本脚本 --fix，或 安装钩子.py（缺它则换机器 clone 后钩子静默失效）'
    txt = read(path)

    if txt is None:
        if not fix:
            rows.append(('x', 'gitattributes', '文件不存在', hint))
            return
        with io.open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(GITATTR_HEAD + '\n' + '\n'.join(GITATTR_LINES) + '\n')
        rows.append(('v', 'gitattributes', '文件不存在 → 已新建（--fix）', ''))
        return

    miss = gitattributes_missing(txt)
    if not miss:
        rows.append(('v', 'gitattributes', 'LF 保护与生成物合并策略齐全', ''))
        return
    if not fix:
        rows.append(('x', 'gitattributes', '缺 %d 行：%s' % (len(miss), '；'.join(miss)),
                     '跑 --fix 自动补（只追加，不动原有内容）'))
        return
    eol = '\r\n' if '\r\n' in txt else '\n'
    prefix = '' if (not txt or txt.endswith(('\n', '\r'))) else eol
    with io.open(path, 'a', encoding='utf-8', newline='') as f:
        f.write(prefix + eol.join(miss) + eol)
    rows.append(('v', 'gitattributes', '缺 %d 行 → 已补（--fix）' % len(miss), ''))


def check_layout(rows):
    doc = os.path.join(ROOT, '开发文档')
    if not os.path.isdir(doc):
        rows.append(('x', '布局', '没有 开发文档/ 目录', '按技能第 E 节建编号目录（00规则 / 01需求 / 02缺陷 / 03技术债 / 04技能）'))
        return
    have = [d for d in LAYOUT if os.path.isdir(os.path.join(doc, d))]
    miss = [d for d in LAYOUT if d not in have]
    if not miss:
        rows.append(('v', '布局', '%d 个编号目录齐全（%s）' % (len(LAYOUT), ' '.join(LAYOUT)), ''))
        return
    for d in miss:
        if d in REQUIRED_DIRS:
            rows.append(('x', '布局', '缺 %s/' % d, '建目录；它装的是流程必需的档案'))
        else:
            rows.append(('d', '布局', '%s/ 未建（跳过阶段可不建）' % d, ''))


def tracked_generated():
    """仍被 git 跟踪的 `_汇总/` 里的文件。非空 ⇒ 并行合并会冲突。"""
    r = git('ls-files', '--', SUMDIR)
    if r.returncode != 0:
        return []
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def check_generated(rows):
    # 顺序很重要：先查「是否入库」，这是并行冲突的直接成因
    stuck = tracked_generated()
    if stuck:
        rows.append(('x', '生成物', '根级视图仍被 git 跟踪：%s' % '、'.join(
            x.split('/')[-1] for x in stuck),
            'git rm --cached 掉并补 .gitignore —— 分片入库、根级视图不入库，否则两人合并必冲突'))

    missing = [p for p in GENERATED if not os.path.isfile(os.path.join(ROOT, p))]
    if missing:
        rows.append(('d', '生成物', '本地还没生成：%s' % '、'.join(
            x.split('/')[-1] for x in missing),
            '跑一次 汇总.py（这些是本地视图，不入库）'))
        return
    sk = proj_skill()
    if not sk:
        rows.append(('d', '生成物', '没有技能副本，跳过新鲜度检查', ''))
        return
    summary = os.path.join(sk, 'scripts', '汇总.py')
    if not os.path.isfile(summary):
        rows.append(('w', '生成物', '技能副本里没有 汇总.py', '重新同步副本'))
        return
    r = subprocess.run([sys.executable, summary, '--check'], cwd=ROOT,
                       capture_output=True, encoding='utf-8', errors='replace')
    if r.returncode == 0:
        rows.append(('v', '生成物', '生成物是最新的', ''))
    else:
        msg = (r.stdout or r.stderr or '').strip().splitlines()
        rows.append(('w', '生成物', '生成物可能过期：%s' % (msg[-1] if msg else 'check 非 0'),
                     '跑 汇总.py 重建'))


# ── 规则四件套：模板是「整份复制 + 填空」，不是「照意思重写」 ──────────────
# 2026-10-26（hld-hj-web 实测）：团队配置.md 5.6 KB → 3.4 KB，审批模式只剩
# 「关键三关　←　G1 / G2 / G3 三处停」一句自编注释，五档可选清单和含义表全丢。
# 文件在、内容瘦了 —— 比缺文件更难发现，所以交给脚本查。
RULE_FILE = '开发文档/00规则/团队配置.md'
APPROVAL_MODES = ('全自动', '仅需求审批', '关键三关', '每阶段', '只在交付验收')
TEST_MODES = ('全量', '仅回归', '仅静态')
NO_GATE_MODES = ('全自动', '仅需求审批', '只在交付验收')


def check_rules(rows):
    """团队配置.md 有没有被写成精简版：档位名、五档清单、含义表、测试三档、人编号。"""
    if not os.path.isdir(os.path.join(ROOT, '开发文档')):
        return
    path = os.path.join(ROOT, RULE_FILE)
    if not os.path.isfile(path):
        rows.append(('x', '规则文件', '缺 %s' % RULE_FILE,
                     '从 references/team-profile.template.md 整份复制到 开发文档/00规则/ 再填空；'
                     '没有它，门禁 / 身份判定 / 取号全得靠猜'))
        return
    text = read(path) or ''
    rel = RULE_FILE

    def pick(keyword):
        """取「- **审批模式**：…」这种字段行：优先列表项，退一步找任意非表格行。

        不能直接取第一个含关键字的行 —— 文件开头的引言常写「…（交付形态 / 审批模式 / 测试策略）」，
        取到它就会误报「没有合法档位名」（2026-10-26 试点2 自测踩到）。"""
        cands = [l for l in text.splitlines()
                 if keyword in l and not l.lstrip().startswith('|')]
        for l in cands:
            if l.lstrip().startswith(('-', '*')):
                return l
        return cands[0] if cands else ''

    line = pick('审批模式')
    if not line:
        rows.append(('x', '规则文件', '%s 里没有「审批模式」这一行' % rel,
                     '五档必须显式选一个写下来，不能靠默认'))
        return

    hits = sorted((line.find(m), m) for m in APPROVAL_MODES if m in line)
    mode = hits[0][1] if hits else ''
    lost = [m for m in APPROVAL_MODES if m not in line]
    if not mode:
        rows.append(('x', '规则文件', '审批模式那行没有合法档位名',
                     '只能写这五个之一：' + '、'.join(APPROVAL_MODES)
                     + '（别写「三关」「仅审需求」这类变体，下一个 agent 认不出来）'))
    elif lost:
        rows.append(('x', '规则文件', '审批模式行丢了 %d 档：%s' % (len(lost), '、'.join(lost)),
                     '行尾必须保留「五档可选：全自动｜仅需求审批｜关键三关｜每阶段｜只在交付验收」；'
                     '只写当前档，等于把别人的选项藏了'))
    absent = [m for m in APPROVAL_MODES if m not in text]
    if mode and len(absent) >= 3:
        rows.append(('x', '规则文件', '「审批模式（五选一）」含义表缺失（5 档只出现 %d 个）' % (5 - len(absent)),
                     '整张表是内容不是占位文字：换档时得靠它判断行为，缺了就只能猜'))

    tline = pick('测试策略')
    tlost = [m for m in TEST_MODES if m not in tline]
    if not tline or len(tlost) == len(TEST_MODES):
        rows.append(('x', '规则文件', '测试策略行缺失或没有档位名',
                     '三选一：' + '、'.join(TEST_MODES)))
    elif tlost:
        rows.append(('w', '规则文件', '测试策略行少了可选档：%s' % '、'.join(tlost),
                     '保留「三档可选：全量｜仅回归｜仅静态」，格式与审批模式行一致'))

    if '人编号' not in text:
        rows.append(('w', '规则文件', '角色表没有「人编号」列',
                     '人编号是 CR 号首位；缺了没法两人并行取号'))

    if mode in NO_GATE_MODES and '不生效' not in text and '无门禁' not in text:
        rows.append(('w', '规则文件', '档位＝%s，但门禁表没标哪些门不生效' % mode,
                     '把 G2/G3 标「本模式不生效」，或整表换成「无门禁」—— 否则读者以为这里真会停'))

    if not any(r[1] == '规则文件' for r in rows):
        rows.append(('v', '规则文件', '%s：档位 %s、五档清单、测试三档、人编号齐全' % (rel, mode), ''))


def check_baseline(rows):
    """基线需求应当有且仅有一条（`需求性质：基线`）。

    基线是「第一版需求」的唯一锚点；没有它，`_汇总/当前需求全貌.md` 就拼不出完整脉络；
    多于一条则说明有人把增量误标成基线，全貌的「基线在前」排序会失真。
    """
    found = []
    for kname in ('01需求', '02缺陷', '03技术债'):
        for rq in glob.glob(os.path.join(ROOT, '开发文档', kname, 'CR-*', '需求.md')):
            with io.open(rq, encoding='utf-8', errors='replace') as f:
                head = f.read(1200)
            if re.search(r'^-\s*需求性质[：:]\s*基线\s*$', head, re.M):
                found.append(os.path.basename(os.path.dirname(rq)))
    if not _cr_dirs():
        rows.append(('d', '基线', '还没有 CR，跳过（首条需求的 需求.md 里写 `- 需求性质：基线`）', ''))
    elif len(found) == 1:
        rows.append(('v', '基线', '1 条基线（%s）' % found[0], ''))
    elif not found:
        rows.append(('w', '基线', '没有任何 CR 标 `需求性质：基线`',
                     '第一版需求要在 `需求.md` 里写 `- 需求性质：基线`，否则全貌视图分不清基线和增量'))
    else:
        rows.append(('x', '基线', '有 %d 条基线：%s' % (len(found), '、'.join(found)),
                     '基线只能有一条。增量 CR 请写 `- 需求性质：增量`（或不写）'))


# `汇总.py` / `自检.py` 硬依赖的字段 —— 每个都该至少有一个分片在写。
# 某字段全项目 0 使用 ⇒ 脚本在解析一个没人产出的东西，等于空转。
CONTRACT_FIELDS = (
    ('需求.md', '变更请求'),
    ('需求.md', '摘要'),
    ('需求.md', '号段'),
    ('需求.md', '需求性质'),
    ('状态.md', '编号'),
    ('状态.md', '名称'),
    ('状态.md', '负责人'),
    ('状态.md', '阶段'),
    ('状态.md', '门禁'),
    ('状态.md', '下一步'),
)


def _cr_dirs():
    out = []
    for k in ('01需求', '02缺陷', '03技术债'):
        out += glob.glob(os.path.join(ROOT, '开发文档', k, 'CR-*'))
    return [d for d in out if os.path.isdir(d)]


def check_dead_rules(rows):
    """死规则检测：脚本/规则依赖的字段，若全项目 0 使用 ⇒ 空转，报警。

    为什么需要：`汇总.py` 曾解析 `需求.md` 里的 `| 修订既有条目 |` 行，而 10 个需求.md
    一个都没写过 —— 那一节永远只有表头，**看着在跑，其实空转**。这类问题读文档发现不了。
    """
    if not _cr_dirs():
        rows.append(('d', '死规则', '还没有 CR，跳过', ''))
        return
    by_name = {}
    for d in _cr_dirs():
        for f in glob.glob(os.path.join(d, '*.md')):
            by_name.setdefault(os.path.basename(f), []).append(f)

    dead = []
    for fname, field in CONTRACT_FIELDS:
        cands = by_name.get(fname, [])
        used = 0
        for f in cands:
            with io.open(f, encoding='utf-8', errors='replace') as fh:
                if re.search(r'^-\s*' + re.escape(field) + r'\s*[：:]', fh.read(), re.M):
                    used += 1
        if used == 0:
            dead.append('%s 的 `%s`' % (fname, field))

    if dead:
        rows.append(('w', '死规则', '%d 个字段全项目没人写：%s' % (len(dead), '、'.join(dead)),
                     '脚本在解析它们 ⇒ 解析结果永远是空。要么补写，要么把这条规则删掉'))
    else:
        rows.append(('v', '死规则', '契约字段都在用（%d 项）' % len(CONTRACT_FIELDS), ''))


def check_orphan_cr(rows):
    """CR 目录里既无 `状态.md` 也无 `需求.md`/`问题.md` ⇒ 汇总会静默跳过它。

    静默丢失比报错危险：一条 CR 干了活、写了文档，却不出现在任何视图里，没人会发现。
    """
    orphan = []
    for d in _cr_dirs():
        if not os.path.isfile(os.path.join(d, '状态.md')) and \
           not os.path.isfile(os.path.join(d, '需求.md')) and \
           not os.path.isfile(os.path.join(d, '问题.md')):
            orphan.append(os.path.basename(d))
    if orphan:
        rows.append(('w', '孤儿 CR', '%d 个 CR 目录缺 状态.md / 需求.md / 问题.md' % len(orphan),
                     '汇总会跳过它们：%s ⇒ 补一个 `状态.md`（阶段可先写 not-started）'
                     % '、'.join(orphan[:3])))
    else:
        rows.append(('v', '孤儿 CR', '每条 CR 都有 状态.md 或 需求.md/问题.md', ''))


def _table(text):
    """取 markdown 第一张表 → [{表头: 单元格}]（与 汇总.py 的 _md_table 同口径）。"""
    head, out = None, []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('|') and s.endswith('|'):
            cells = [c.strip() for c in s[1:-1].split('|')]
            if head is None:
                head = cells
                continue
            if cells and all(set(c) <= set('-: ') for c in cells):
                continue
            out.append(dict(zip(head, cells)))
        elif out:
            break
    return out


def _get(row, key):
    """按表头前缀取值（表头可能写成「触发信号（怎么知道它发生了）」）。"""
    if key in row:
        return row[key]
    for k, v in row.items():
        if k.startswith(key):
            return v
    return '—'


def _crno(d):
    """目录名 → CR 号。`CR-16102999-反向验证` → `CR-16102999`。

    不能用 `split('-', 1)[0]`：那只会得到 "CR"，报错信息里就看不出是哪一条。
    """
    m = re.match(r'(CR[-_]?\d+)', os.path.basename(d))
    return m.group(1) if m else os.path.basename(d)


def _base(v):
    """去掉括号说明：`已接受（成本>收益）` → `已接受`。"""
    return re.split(r'[（(]', (v or '').strip(), maxsplit=1)[0].strip()


def _started(cr):
    """这条 CR 是否已经开工。not-started / cancelled 算没开工。"""
    p = os.path.join(cr, '状态.md')
    if not os.path.isfile(p):
        return False
    with io.open(p, encoding='utf-8', errors='replace') as f:
        m = re.search(r'^-\s*阶段[：:]\s*(.+)$', f.read(), re.M)
    stage = (m.group(1) if m else '').strip().lower()
    return not ('not-started' in stage or 'cancelled' in stage or not stage)


def check_resources(rows):
    """前置资源没到位却已经开工 ⇒ 判错。

    `前置资源.md` 里 `必需 + 待提供` 意味着「缺了做不了」。若这条 CR 的阶段已经推进
    （不是 not-started / cancelled），说明在资源没到的情况下开工了 —— 这正是要防的。
    """
    bad, total_file = [], 0
    for d in _cr_dirs():
        p = os.path.join(d, '前置资源.md')
        if not os.path.isfile(p):
            continue
        total_file += 1
        with io.open(p, encoding='utf-8', errors='replace') as f:
            items = _table(f.read())
        missing = [_get(it, '资源') for it in items
                   if _get(it, '必需性') == '必需' and _base(_get(it, '状态')) == '待提供']
        if missing and _started(d):
            bad.append('%s（缺：%s）' % (_crno(d), '、'.join(missing[:3])))
    if bad:
        rows.append(('x', '前置资源', '%d 条 CR 在必需资源「待提供」时就开工了' % len(bad),
                     '；'.join(bad[:3]) + ' ⇒ 要么等资源，要么在 `前置资源.md` 写明降级方案并改状态'))
    elif total_file:
        rows.append(('v', '前置资源', '%d 条 CR 登记了前置资源，无「必需且待提供」' % total_file, ''))
    else:
        rows.append(('d', '前置资源', '还没有 CR 写 前置资源.md', '有外部依赖的 CR（模型/设计图/API Key/设备）应写'))


def check_risks(rows):
    """高风险仍「待处理」，但 CR 还在做 ⇒ 建议确认（不判错）。

    只查「影响=高」：中低风险本来就是边做边看，天天提醒等于噪音。
    """
    hot, total_file = [], 0
    for d in _cr_dirs():
        p = os.path.join(d, '风险.md')
        if not os.path.isfile(p):
            continue
        total_file += 1
        if not _started(d):
            continue        # 还没开工的 CR，风险刚登记、本来就没处理，提醒是噪音
        with io.open(p, encoding='utf-8', errors='replace') as f:
            items = _table(f.read())
        for it in items:
            if _get(it, '影响') == '高' and _base(_get(it, '状态')) in ('待处理', '已发生'):
                hot.append('%s/%s' % (_crno(d), _get(it, '编号')))
    if hot:
        rows.append(('w', '风险', '%d 条高影响风险仍未处理：%s' % (len(hot), '、'.join(hot[:3])),
                     '确认是否已知悉；处理完把状态改成「已缓解」或「已接受」'))
    elif total_file:
        rows.append(('v', '风险', '%d 条 CR 登记了风险，无未处理的高影响项' % total_file, ''))
    else:
        rows.append(('d', '风险', '还没有 CR 写 风险.md', ''))


def check_numbers(rows):
    """检查 CR 号有没有重复。

    号写在**目录名**里（`CR-<8位号>-<简称>`），不再有单独的「号段文件」——
    目录名就是占位凭据，同号必然撞同一路径。
    """
    seen = {}
    dup = []
    # CR 直接挂在类型目录下：开发文档/01需求/CR-xxx、02缺陷/CR-xxx、03技术债/CR-xxx
    for kname in ('01需求', '02缺陷', '03技术债'):
        kdir = os.path.join(ROOT, '开发文档', kname)
        if not os.path.isdir(kdir):
            continue
        for d in os.listdir(kdir):
            if not os.path.isdir(os.path.join(kdir, d)) or not d.startswith('CR'):
                continue
            m = re.match(r'CR[-_]?(\d+)', d)
            if not m:
                continue
            no = m.group(1)
            if no in seen:
                dup.append('%s 与 %s' % (seen[no], d))
            else:
                seen[no] = d
    if dup:
        rows.append(('x', '编号', 'CR 号重复：%s' % '；'.join(dup),
                     '两条 CR 用同一个号 ⇒ 目录名必须不同。号是「人+年末位+月日+当日序号」算出来的，重算'))
    else:
        rows.append(('v', '编号', '%d 条 CR，编号无重复' % len(seen), ''))


# ── 规则四件套：模板是「整份复制 + 填空」，不是「照意思重写」 ──────────────
# 2026-10-26（hld-hj-web 实测）：团队配置.md 5.6 KB → 3.4 KB，审批模式只剩
# 「关键三关　←　G1 / G2 / G3 三处停」一句自编注释，五档可选清单和含义表全丢。
# 文件在、内容瘦了 —— 比缺文件更难发现，所以交给脚本查。
RULE_PATHS = ('开发文档/00规则/团队配置.md', '开发文档/规则/团队配置.md',
              '规则/团队配置.md', '开发文档/团队配置.md')
APPROVAL_MODES = ('全自动', '仅需求审批', '关键三关', '每阶段', '只在交付验收')
TEST_MODES = ('全量', '仅回归', '仅静态')
NO_GATE_MODES = ('全自动', '仅需求审批', '只在交付验收')


# 输出符号：v=通过 / w=建议 / x=问题 / d=跳过
GLYPH = {'v': '✓', 'w': '!', 'x': '✗', 'd': '·'}

def main():
    argv = sys.argv[1:]
    fix = '--fix' in argv
    quiet = '--quiet' in argv

    rows = []
    check_anchors(rows)
    check_skill_copy(rows)
    check_hooks(rows)
    check_gitattributes(rows, fix)
    check_layout(rows)
    check_rules(rows)
    check_generated(rows)
    check_numbers(rows)
    check_baseline(rows)
    check_resources(rows)
    check_risks(rows)
    check_dead_rules(rows)
    check_orphan_cr(rows)

    print('AIDLC 自检  %s' % ROOT)
    print('-' * 60)
    for lv, name, detail, fixhint in rows:
        if quiet and lv == 'v':
            continue
        print('%s %-13s %s' % (GLYPH[lv], name, detail))
        if fixhint:
            print('  └ %s' % fixhint)

    nv = sum(1 for r in rows if r[0] == 'v')
    nw = sum(1 for r in rows if r[0] == 'w')
    nx = sum(1 for r in rows if r[0] == 'x')
    nd = sum(1 for r in rows if r[0] == 'd')
    print('-' * 60)
    print('%d 通过 · %d 建议 · %d 问题 · %d 跳过' % (nv, nw, nx, nd))
    if nx:
        print('有 %d 个真问题，按上面的「└」修；改不了再问人。' % nx)
        return 1
    if nw:
        print('能跑，但有 %d 条建议 —— 现在不修，换机器/换人时就会变成问题。' % nw)
        return 2
    print('全绿。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
