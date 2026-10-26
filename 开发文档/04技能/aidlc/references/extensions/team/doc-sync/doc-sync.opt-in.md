# 文档同步 — Opt-In

**Extension**: Doc Sync

## Opt-In Prompt

以下问题会在需求分析阶段的澄清问题里自动出现：

```markdown
## Question: 文档同步
代码改动后，是否强制把受影响的阶段文档一起更新（避免 spec 与代码脱节）？

A) 是 — 每次代码变更后检查并更新受影响的 aidlc-docs/ 文档，记入 audit（推荐）
B) 仅关键改动 — 只在需求/设计变更时同步，纯实现细节不动文档
C) 否 — 不强制同步（短周期项目）
X) 其他（请在 [Answer]: 后说明）

[Answer]: 
```
