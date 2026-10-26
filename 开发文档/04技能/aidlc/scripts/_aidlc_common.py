# -*- coding: utf-8 -*-
"""AIDLC 脚本共用常量 —— 只放「两个以上脚本都要用」的东西。

为什么不各写一份：2026-10-21 一天里，「同一规则两处定义」已经造成两次腐化
（技能副本落点写死 `skills/`、`.gitattributes` 只在一处补）。规则只能有一个来源。
"""

GITATTR_HEAD = '# AIDLC：git 钩子必须是 LF —— CRLF 会让 shebang 失效，钩子静默不执行'

GITATTR_LINES = (
    '*.sh text eol=lf',
    '.gitattributes text eol=lf',
    '**/scripts/hooks/* text eol=lf',
)

# 所有跨 CR 的视图都收口到 `开发文档/_汇总/`：整个目录**本地生成、不入库**。
#
# 为什么：它们是「扫各 CR 分片算出来的」。只要入库，两条并行线各自跑过汇总内容必然不同
# （各自多一行 CR、生成时间也不同）→ 合并时三方合并必冲突，而手工解冲突毫无意义。
# 2026-10-21 实测：两个并行 CR 合并时 `状态.md` 冲突 5 处、`需求索引.md` 3 处，全是纯生成物；
# 换成按 CR 拆目录 + 视图集中到 _汇总/ 后，冲突面只剩源代码。
#
# 真实来源永远是分片：`<类型目录>/CR-XXXX/{需求,状态,设计,测试记录,验收报告,问题,运维说明,变更说明,审计-<人>}.md`
GENERATED_DIR = '开发文档/_汇总/'
GENERATED_IGNORE = (
    GENERATED_DIR,
    # Python 字节码缓存：技能副本里的脚本 import 同目录模块时会生成，
    # 不同 Python 版本文件名不同（cpython-311 / 313），一旦入库就会互相污染。
    '__pycache__/',
    '*.pyc',
)

GITIGNORE_HEAD = '# AIDLC：生成物与 Python 缓存，都不入库（视图本地生成；pyc 跨版本会互相污染）'


def gitattributes_missing(text):
    """返回 .gitattributes 里缺的行（用于幂等补齐）。"""
    have = set(l.strip() for l in text.splitlines())
    return [l for l in GITATTR_LINES if l not in have]


def gitignore_missing(text):
    """返回 .gitignore 里缺的生成物行（用于幂等补齐）。"""
    have = set(l.strip().replace('\\', '/').lstrip('/') for l in text.splitlines())
    return [l for l in GENERATED_IGNORE if l not in have]
