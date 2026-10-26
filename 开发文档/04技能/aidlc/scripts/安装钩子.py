#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安装 git 钩子：让 clean merge / 冲突解决后提交 / rebase 之后自动重建文档视图。

钩子文件就在本脚本旁边的 `hooks/`，随 AIDLC 技能副本一起走；但 git 默认只读 `.git/hooks/`，
所以**每个克隆都要跑一次**本脚本，把 `core.hooksPath` 指过去。

  python <技能副本>/scripts/安装钩子.py            # 安装
  python <技能副本>/scripts/安装钩子.py --status   # 只看当前配置
  python <技能副本>/scripts/安装钩子.py --uninstall

为什么挂三个钩子（实测结论，别只挂 post-merge）：
  干净合并 / fast-forward        → post-merge
  冲突解决后 `git commit` 收尾   → post-commit（父提交数为 2），post-merge **不触发**
  rebase 收尾（含 --continue）   → post-rewrite
"""

import os
import sys
import stat
import subprocess

# 不生成 __pycache__：技能副本是只读资源，在里面写字节码会污染项目（git 还会看见）
sys.dont_write_bytecode = True

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _aidlc_common import (GITATTR_HEAD, GITATTR_LINES, GITIGNORE_HEAD,  # noqa: E402
                           GENERATED_IGNORE, gitattributes_missing, gitignore_missing)

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.join(HERE, 'hooks')          # 与脚本同级，随技能副本走
SUMMARY = os.path.join(HERE, '汇总.py')
HOOKS = ('post-merge', 'post-commit', 'post-rewrite', '_summary.sh')


def _project_root(start):
    """找项目根：先问 git，再退回「往上找含 开发文档/ 的目录」。

    注意 `encoding='utf-8'`：不能用 `text=True`。Windows 下 text 模式按 locale（cp936/GBK）
    解码 git 的 UTF-8 输出，中文路径会被解成乱码，再交给 `cwd=` 就是 WinError 267
    （ERROR_DIRECTORY，目录名无效）。2026-10-21 在中文路径项目上实测踩到。
    """
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
            raise SystemExit('找不到项目根（从 %s 往上）' % start)
        d = parent


ROOT = _project_root(HERE)
REL = os.path.relpath(HOOKS_DIR, ROOT).replace(os.sep, '/')
REL_SUM = os.path.relpath(SUMMARY, ROOT).replace(os.sep, '/')


def git(*args):
    return subprocess.run(['git'] + list(args), cwd=ROOT,
                          capture_output=True, encoding='utf-8', errors='replace')


def status():
    cur = git('config', '--local', '--get', 'core.hooksPath').stdout.strip()
    print('项目根        %s' % ROOT)
    print('钩子目录      %s' % REL)
    print('汇总脚本      %s' % REL_SUM)
    print('core.hooksPath = %s' % (cur or '(未设置，用默认 .git/hooks)'))
    for h in HOOKS:
        print('  %-14s %s' % (h, '存在' if os.path.exists(os.path.join(HOOKS_DIR, h)) else '缺失'))
    gp = os.path.join(ROOT, '.gitattributes')
    if not os.path.exists(gp):
        gstate = '缺失 ⚠ 重新克隆后钩子会变 CRLF 而静默失效（跑安装即补）'
    else:
        with open(gp, 'rb') as f:
            have = set(l.strip() for l in f.read().decode('utf-8', 'replace').splitlines())
        miss = [l for l in GITATTR_LINES if l not in have]
        gstate = '齐全' if not miss else '缺 %d 行：%s' % (len(miss), '；'.join(miss))
    print('.gitattributes  %s' % gstate)
    gi = os.path.join(ROOT, '.gitignore')
    if not os.path.exists(gi):
        gistate = '缺失 ⚠ 生成物会入库，并行合并必冲突（跑安装即补）'
    else:
        with open(gi, 'rb') as f:
            ghave = f.read().decode('utf-8', 'replace')
        gistate = '生成物已排除' if not gitignore_missing(ghave) else \
            '缺 %d 行生成物排除规则' % len(gitignore_missing(ghave))
    print('.gitignore     %s' % gistate)
    stuck = tracked_generated()
    print('生成物跟踪     %s' % ('⚠ 仍被跟踪：%s' % '、'.join(stuck) if stuck
                             else '未入库（本地生成，正确）'))
    ok = (cur == REL)
    print('\n状态：%s' % ('已启用' if ok else '未启用（跑 `python %s`）' % REL_SUM.replace('汇总.py', '安装钩子.py')))
    return 0 if ok else 1


def chmod_x():
    for h in HOOKS:
        p = os.path.join(HOOKS_DIR, h)
        if not os.path.exists(p):
            continue
        try:
            os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass  # Windows 上 chmod 意义有限，git for windows 自行判断


def ensure_gitattributes():
    """补 `.gitattributes` 的 LF 保护行 + 生成物的合并策略。幂等：只补缺的行，不动用户已有内容。

    为什么归钩子管：钩子文件随技能走、必须一直是 LF。少了这几行，本机现在能用，
    但**换机器 / 重新 clone 就会失效**——而且失效时没有任何报错，只有「视图怎么不更新了」。
    """
    path = os.path.join(ROOT, '.gitattributes')
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(GITATTR_HEAD + '\n' + '\n'.join(GITATTR_LINES) + '\n')
        return 'create'

    with open(path, 'rb') as f:
        raw = f.read()
    eol = '\r\n' if b'\r\n' in raw else '\n'
    text = raw.decode('utf-8', 'replace')
    missing = gitattributes_missing(text)
    if not missing:
        return 'unchanged'

    prefix = '' if (not text or text.endswith(('\n', '\r'))) else eol
    body = GITATTR_HEAD + eol if not text.strip() else ''
    with open(path, 'a', encoding='utf-8', newline='') as f:
        f.write(prefix + body + eol.join(missing) + eol)
    return 'append %d 行' % len(missing)


def ensure_gitignore():
    """把三个生成物写进 `.gitignore`（幂等，只补缺行）。

    生成物是「扫分片算出来的视图」，入库就会在并行合并时三方冲突。不入库 + 本地生成，
    冲突面就只剩源代码和手写文档 —— 而文档本身是一人一目录，天然不冲突。
    """
    path = os.path.join(ROOT, '.gitignore')
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(GITIGNORE_HEAD + '\n' + '\n'.join(GENERATED_IGNORE) + '\n')
        return 'create'

    with open(path, 'rb') as f:
        raw = f.read()
    eol = '\r\n' if b'\r\n' in raw else '\n'
    text = raw.decode('utf-8', 'replace')
    missing = gitignore_missing(text)
    if not missing:
        return 'unchanged'

    prefix = '' if (not text or text.endswith(('\n', '\r'))) else eol
    body = GITIGNORE_HEAD + eol if not text.strip() else ''
    with open(path, 'a', encoding='utf-8', newline='') as f:
        f.write(prefix + body + eol.join(missing) + eol)
    return 'append %d 行' % len(missing)


def tracked_generated():
    """仍被 git 跟踪的生成物（相对路径列表）。非空 ⇒ 并行合并迟早冲突。"""
    r = git('ls-files', '--', *GENERATED_IGNORE)
    if r.returncode != 0:
        return []
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def main():
    argv = sys.argv[1:]
    if '--status' in argv:
        return status()

    if '--uninstall' in argv:
        git('config', '--local', '--unset', 'core.hooksPath')
        print('已卸载：core.hooksPath 已清除（钩子文件仍留在 %s，未删除）' % REL)
        return 0

    if not os.path.isdir(HOOKS_DIR):
        print('找不到钩子目录 %s，无法安装（技能副本可能不完整）' % HOOKS_DIR)
        return 2

    chmod_x()
    attr = ensure_gitattributes()
    ign = ensure_gitignore()
    r = git('config', '--local', 'core.hooksPath', REL)
    if r.returncode != 0:
        print('设置 core.hooksPath 失败：%s' % r.stderr.strip())
        return 2

    print('已启用 git 钩子：core.hooksPath = %s' % REL)
    print('.gitattributes LF 保护：%s' % ('已存在，无需改动' if attr == 'unchanged' else
                                     ('新建' if attr == 'create' else '补上 ' + attr.split(' ', 1)[1])))
    print('.gitignore 生成物排除：%s' % ('已存在，无需改动' if ign == 'unchanged' else
                                    ('新建' if ign == 'create' else '补上 ' + ign.split(' ', 1)[1])))
    stuck = tracked_generated()
    if stuck:
        print('⚠ 以下生成物仍被 git 跟踪，并行合并照样会冲突：')
        for p in stuck:
            print('    %s' % p)
        print('  一次性移除：git rm --cached --%s' % ''.join(' "%s"' % p for p in stuck))
    print('生效时机：clean merge（post-merge）｜ 冲突解决后提交（post-commit，父提交数=2）｜ rebase 收尾（post-rewrite）')
    print('动作：跑 %s 在本地重建 开发文档/_汇总/ 下的 8 个视图（视图不入库，不 git add）' % REL_SUM)
    print('      若 00规则/团队配置.md 里声明了「构建命令」，再执行它')
    print('任何失败都不会阻塞 git（顶多视图过期）。')
    print('\n提示：core.hooksPath 是本仓库的本地配置，换机器 / 重新克隆要再跑一次。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
