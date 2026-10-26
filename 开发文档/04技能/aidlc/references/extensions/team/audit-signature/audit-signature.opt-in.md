# 审计签名 — Opt-In

**Extension**: Audit Signature

## Opt-In Prompt

以下问题会在需求分析阶段的澄清问题里自动出现：

```markdown
## Question: 审计签名
是否给 audit.md 的每条记录签署身份（User / Email）？

A) 是 — 从 `git config user.name` / `user.email` 取值，每条记录带身份（团队协作推荐）
B) 否 — 只记时间戳和内容（单人自用）
X) 其他（请在 [Answer]: 后说明）

[Answer]: 
```
