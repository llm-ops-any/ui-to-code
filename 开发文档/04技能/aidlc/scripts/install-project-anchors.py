#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIDLC 项目锚点安装器

做两件事：
1. 把「本项目所有需求先走 AIDLC」写进各平台各自的「项目规则 / 项目记忆」文件；
2. （可选）把技能本身复制到项目内，让项目自包含。落点**固定**：
   `开发文档/04技能/aidlc/`，不探测其它位置。

只依赖标准库，Windows / macOS / Linux 通用。

保证
- 幂等：靠 `<!-- AIDLC:v2 BEGIN --> … <!-- AIDLC:v2 END -->` 定位，重复运行不写重复内容；
  旧版本标记（v1）也能识别并整段替换，不会重复追加
- 不覆盖：已有文件只在末尾追加，或整段替换标记区间，用户原文逐字节保留
- 可卸载：--remove 只删标记区间，只剩空壳时连文件一起删
- 行尾跟随：目标用 CRLF 就写 CRLF，不翻整个文件

用法
    python install-project-anchors.py                    # 装到当前目录，自动探测平台
    python install-project-anchors.py --dry-run           # 只看会改哪些文件
    python install-project-anchors.py D:/path/to/proj     # 指定项目根
    python install-project-anchors.py --with-skill        # 同时复制 开发文档/04技能/aidlc/
    python install-project-anchors.py --platforms agents,claude
    python install-project-anchors.py --platforms claude --full   # 只在 CLAUDE.md 放全文，不碰 AGENTS.md
    python install-project-anchors.py --remove            # 卸载标记段
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

VERSION = 'v2'
BEGIN = '<!-- AIDLC:%s BEGIN' % VERSION
END = '<!-- AIDLC:%s END -->' % VERSION

# 版本容忍：v1 装过的项目再跑，应被整段替换而不是重复追加
ANY_BEGIN = re.compile(r'<!-- AIDLC:v\d+ BEGIN[^>]*-->')
ANY_END = re.compile(r'<!-- AIDLC:v\d+ END -->')
FRONTMATTER = re.compile(r'^\s*---\r?\n.*?\r?\n---\r?\n', re.S)
MDC_HEADER = '---\ndescription: 本项目所有需求先走 AIDLC\nalwaysApply: true\n---\n\n'

POINTER_BODY = """## 本项目必须走 AIDLC

本工作区的**所有**需求、任务、改动、问题排查，先读项目根 `AGENTS.md` 与 `开发文档/状态.md`，
按 AIDLC 流程推进，**不得直接产出代码、脚本或部署产物**。

- 新需求 / 改需求 / 改界面 → 登记变更请求（CR），按迭代走
- 部署 / 上线 / 发布 / 改域名 → 是变更请求，不是运维杂活
- 性能优化 / 重构 → 先测量给数字
- 缺陷 / 报错 → 登记后按缺陷流程走
- **可以直接回答、不进流程的只有**：纯问答、解释代码、读文件

> 规则细则见项目根 `AGENTS.md`；宿主未加载 aidlc 技能时，读 `开发文档/04技能/aidlc/SKILL.md`。
"""


def block_pointer():
    return '%s —— 由 aidlc 技能维护，删除本段即表示本项目不走 AIDLC -->\n%s%s\n' % (BEGIN, POINTER_BODY, END)


def read_text(path):
    try:
        return path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return None
    except UnicodeDecodeError:
        return path.read_text(encoding='utf-8', errors='replace')


def _norm(s):
    """比较用：统一换行并去首尾空白（git autocrlf 会把 LF 存成 CRLF）"""
    return s.replace('\r\n', '\n').strip()


def _match_eol(block, existing):
    if existing and '\r\n' in existing:
        return block.replace('\n', '\r\n')
    return block


def _region(text):
    """返回 (state, start, end)，state ∈ none / ok / broken"""
    m = ANY_BEGIN.search(text)
    if not m:
        return 'none', -1, -1
    e = ANY_END.search(text, m.start())
    if not e:
        return 'broken', m.start(), -1
    return 'ok', m.start(), e.end()


def plan(path, new_block):
    text = read_text(path)
    if text is None:
        return 'create', '新建'
    block = _match_eol(new_block, text)
    state, start, end = _region(text)
    if state == 'none':
        return 'append', '末尾追加（原文未动）'
    if state == 'broken':
        return 'error', '标记不完整（有 BEGIN 无 END）'
    if _norm(text[start:end]) == _norm(block):
        return 'unchanged', '已是当前版本'
    return 'replace', '整段替换标记区间'


def upsert(path, new_block, header=''):
    text = read_text(path)
    if text is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(header + new_block, encoding='utf-8')
        return 'create', '新建'

    block = _match_eol(new_block, text)
    state, start, end = _region(text)
    if state == 'none':
        sep = '' if text.endswith('\n\n') else ('\n' if text.endswith('\n') else '\n\n')
        if '\r\n' in text and sep:
            sep = sep.replace('\n', '\r\n')
        path.write_text(text + sep + block, encoding='utf-8')
        return 'append', '末尾追加（原文未动）'
    if state == 'broken':
        return 'error', '标记不完整（有 BEGIN 无 END），未改动'
    if _norm(text[start:end]) == _norm(block):
        return 'unchanged', '已是当前版本'

    path.write_text(text[:start] + block.strip() + text[end:], encoding='utf-8')
    return 'replace', '整段替换标记区间'


def remove_block(path):
    text = read_text(path)
    if text is None:
        return 'skip', '文件不存在'
    state, start, end = _region(text)
    if state == 'none':
        return 'skip', '没有 AIDLC 段'
    if state == 'broken':
        return 'error', '标记不完整，未改动'

    rest = (text[:start] + text[end:]).rstrip() + '\n'
    if rest.strip() == '' or FRONTMATTER.sub('', rest).strip() == '':
        path.unlink()
        return 'deleted', '仅剩空壳，已删除文件'
    path.write_text(rest, encoding='utf-8')
    return 'removed', '仅移除标记段'


def detect_targets(root, home):
    """哪些平台要写锚点。两条口径（2026-10-26 张勇定）：

    1. **`AGENTS.md` 与 `CLAUDE.md` 始终写** —— 它们是通用入口，几乎所有 agent 都认；
    2. **其余平台「项目里已有对应目录」才写** —— 不再看用户主目录有没有装那个 IDE。
       理由：`~/.cursor` 装过 Cursor 不代表这个项目用 Cursor；按 home 探测会在别人的仓库里
       造出一堆没人读的 `.windsurf/rules/aidlc.md`，还得解释它们是什么。
    """
    found = [
        ('agents', 'AGENTS.md', 'full', '通用约定，始终安装'),
        ('claude', 'CLAUDE.md', 'pointer', 'Claude Code 及兼容工具入口，始终安装'),
    ]

    if (root / '.cursor').exists():
        found.append(('cursor', '.cursor/rules/aidlc.mdc', 'mdc', '项目里有 .cursor/'))

    if (root / '.windsurf').exists():
        found.append(('windsurf', '.windsurf/rules/aidlc.md', 'pointer', '项目里有 .windsurf/'))

    if (root / '.github').exists():
        found.append(('copilot', '.github/copilot-instructions.md', 'pointer', '项目里有 .github/'))

    if (root / '.trae').exists():
        found.append(('trae', '.trae/rules/aidlc.md', 'pointer', '项目里有 .trae/'))

    # CodeBuddy 规则默认全局（~/.codebuddy/rules），项目级不一定被读；
    # 只在项目里已存在 .codebuddy 时写，避免制造死文件
    if (root / '.codebuddy').exists():
        found.append(('codebuddy', '.codebuddy/rules/aidlc.mdc', 'mdc', '项目里有 .codebuddy/'))

    if (root / '.workbuddy').exists():
        found.append(('workbuddy', '.workbuddy/memory/MEMORY.md', 'pointer', '项目里有 .workbuddy/'))

    return found


def list_skill_files(src):
    return sorted(
        p for p in src.rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and not p.name.endswith('.pyc')
    )


def _skill_dest(root):
    """技能副本落哪：**固定** `开发文档/04技能/aidlc/`，不做「已有位置优先」。

    > 2026-10-21 修：默认落点原来写死 `skills/aidlc/`，与技能布局打架，新项目落到项目根，
    > AGENTS.md 里的路径也跟着指错。落点必须跟着布局走。
    > 落点固定是为了「副本在哪」可预测：探测式落点会让新项目落到项目根，工具又只认这里。"""
    return root / '开发文档' / '04技能' / 'aidlc'


def sync_skill(src, dest, dry_run):
    """把技能树复制到 <project>/开发文档/04技能/aidlc。返回 (action, note)"""
    files = list_skill_files(src)
    if not dest.exists():
        if not dry_run:
            for f in files:
                target = dest / f.relative_to(src)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
        return 'create', '复制 %d 个文件' % len(files)

    want = {f.relative_to(src): f for f in files}
    missing = [r for r in want if not (dest / r).exists()]
    changed = [r for r in want if (dest / r).exists() and (dest / r).stat().st_size != want[r].stat().st_size]
    have = {p.relative_to(dest) for p in dest.rglob('*') if p.is_file()}
    extra = [r for r in have if r not in want]

    if not missing and not changed and not extra:
        return 'unchanged', '与技能源一致（%d 个文件）' % len(files)

    if not dry_run:
        for f in files:
            target = dest / f.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
        # 多余文件只报告不删——可能是用户自己的本地改动
    note = []
    if missing:
        note.append('新增 %d' % len(missing))
    if changed:
        note.append('更新 %d' % len(changed))
    if extra:
        note.append('多余 %d（未删）' % len(extra))
    return 'sync', '，'.join(note)


def main():
    ap = argparse.ArgumentParser(description='把 AIDLC 项目规则写进各平台的项目记忆/规则文件')
    ap.add_argument('root', nargs='?', default='.', help='项目根目录（默认当前目录）')
    ap.add_argument('--platforms', default='auto',
                    help='auto 或逗号分隔：agents,claude,cursor,windsurf,copilot,trae,codebuddy,workbuddy')
    ap.add_argument('--dry-run', action='store_true', help='只显示将要做什么')
    ap.add_argument('--remove', action='store_true', help='卸载标记段')
    ap.add_argument('--template', default=None, help='AGENTS.md 模板路径（默认取技能自带模板）')
    ap.add_argument('--with-skill', action='store_true', help='同时把技能复制到 <项目>/开发文档/04技能/aidlc')
    ap.add_argument('--skill-only', action='store_true', help='只同步技能，不写各平台锚点')
    ap.add_argument('--full', action='store_true',
                    help='指针型平台（CLAUDE.md / .windsurf / copilot）也写全文规范，而不是只放一句指针')
    args = ap.parse_args()

    root = Path(args.root).resolve()
    home = Path.home()
    if not root.is_dir():
        print('✗ 不是目录：%s' % root)
        return 2

    here = Path(__file__).resolve().parent
    skill_src = here.parent
    tpl = Path(args.template) if args.template else (skill_src / 'references' / 'project-agents.template.md')
    if not args.skill_only and not tpl.exists():
        print('✗ 找不到模板：%s' % tpl)
        return 2
    template_text = '' if args.skill_only else tpl.read_text(encoding='utf-8')

    targets = [] if args.skill_only else detect_targets(root, home)
    if args.platforms != 'auto' and targets:
        wanted = set(p.strip() for p in args.platforms.split(',') if p.strip())
        targets = [t for t in targets if t[0] in wanted]
        known = {'agents', 'claude', 'cursor', 'windsurf', 'copilot', 'trae',
                 'codebuddy', 'workbuddy'}
        unknown = wanted - known
        if unknown:
            print('! 未识别的平台，已忽略：%s' % ', '.join(sorted(unknown)))

    print('项目根：%s' % root)
    print('模式：%s' % ('卸载' if args.remove else ('预演（不写盘）' if args.dry_run else '安装')))
    print('')

    rows = []
    for key, rel, kind, why in targets:
        path = root / rel
        if args.remove:
            if args.dry_run:
                text = read_text(path) or ''
                action, note = ('would-remove', '预演') if ANY_BEGIN.search(text) else ('skip', '没有 AIDLC 段')
            else:
                action, note = remove_block(path)
        else:
            # `--full`：本来只放「指针」的平台（CLAUDE.md / .windsurf / copilot）改放全文规范。
            # 用于「项目自己的 AGENTS.md 不许改，AIDLC 整套规范只能落在 CLAUDE.md」这种场景。
            kind2 = 'full' if (args.full and kind == 'pointer') else kind
            body = (template_text.strip() + '\n') if kind2 == 'full' else block_pointer()
            header = MDC_HEADER if kind2 == 'mdc' else ''
            if args.dry_run:
                action, note = plan(path, body)
                action, note = 'would-' + action, '预演'
            else:
                action, note = upsert(path, body, header)
        rows.append((rel, action, note, why))

    if args.with_skill or args.skill_only:
        dest = _skill_dest(root)
        if args.dry_run:
            action, note = sync_skill(skill_src, dest, True)
            action = 'would-' + action
        else:
            action, note = sync_skill(skill_src, dest, False)
        rows.append((dest.relative_to(root).as_posix() + '/', action, note, '项目自包含技能副本'))

    if not rows:
        print('没有命中任何目标。用 --platforms 指定，或加 --with-skill。')
        return 0

    w = max(len(r[0]) for r in rows)
    for rel, action, note, why in rows:
        flag = '✗' if action == 'error' else ('·' if action in ('unchanged', 'skip') else '✓')
        print('%s %-*s  %-13s %s' % (flag, w, rel, action, note))
        print('   └ %s' % why)

    bad = [r for r in rows if r[1] == 'error']
    print('')
    print('完成：%d 个目标，%d 个异常' % (len(rows), len(bad)))
    if bad:
        print('! 异常目标需要人工处理：%s' % ', '.join(r[0] for r in bad))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
