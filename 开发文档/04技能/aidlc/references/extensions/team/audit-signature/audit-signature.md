# 审计签名

**启用后本规则是硬约束。**

## 为什么

默认的 `audit.md` 只有时间戳和内容。团队协作时，你看得到「谁提的需求」记录不下来，
出问题时只能靠猜或翻 git 历史对时间。加上身份字段，每条历史都能直接追到人。

## 身份来源（按顺序取第一个可用的）

1. 项目根 `.aidlc-owner` 文件，格式两行：
   ```
   user: 张勇
   email: zhangyong@example.com
   ```
2. `git config user.name` / `git config user.email`（在项目目录里执行）
3. 都取不到 → 问用户一次，得到的答案写进 `.aidlc-owner`，后续复用

**不要凭猜填名字或邮箱。** 取不到就问，一次。

## 记录格式（覆盖 SKILL.md 第 0.C 节的默认格式）

```markdown
## [阶段名 或 交互类型]
**Timestamp**: 2026-10-18T05:40:12+08:00
**User**: 张勇
**Email**: zhangyong@example.com
**User Input**: "用户原始输入，一字不改，不概括"
**AI Response**: "AI 做了什么、说了什么"
**Context**: 阶段 / 动作 / 决策
```

审批类记录再加一行 `**Role**: approver | executor | reviewer`，用来区分「谁批的」和「谁执行的」。

## 边界

- **只对启用之后的记录签名**。历史条目不要回填——回填等于伪造时间线。
- 在启用时的第一条记录里写明：`启用 audit-signature，此前条目无签名`。
- 用户输入里如果自己报了名字，以用户说的为准，并提示与 git 配置不一致。
