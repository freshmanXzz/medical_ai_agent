# Martin 长期记忆 V2.2 实施基线

核对日期：2026-10-09。执行依据：`docs/plans/MARTIN_MEMORY_V22_EXECUTION_PLAN.md`，从用户提供的 `Martin_V2_2_Plan.md` 原样保存。八项已确认决策沿用，不重新选择。

## 1. Git 与可回滚基线

- 分支：`codex/memory-v21-governance`。
- HEAD：`b8fd8b385f3de6d467c7fe7b364b12f800ba1c6c`。
- V2.1 的实现与验收文档仍在工作区，尚未固化为提交；本轮未提交、未推送。
- 实施前将 34 个相关文件的工作区版本、完整 tracked diff 和 SHA256 清单保存至被忽略的 `tmp/v22-baseline-20261009/`。其中包括已有用户文档修改，不能以 V2.2 的名义覆盖。
- `data/`、`output/`、其它 `tmp/` 文件、本地医学资料与未跟踪脚本未清理，未迁移运行库。
- 后续若需要提交，可单独挑选 V2.1 实现和验收文档形成 baseline 提交，再按批次提交 V2.2；不将未知文件纳入。本轮用快照保存基线，提交待另行授权。

## 2. 现状与缺口

| 能力 | 实施前代码现状 | V2.2 处理 |
| --- | --- | --- |
| 九类记忆、Exact / Temporal / Semantic、统一 Router | 已有 | 复用来源、权限、生命周期过滤 |
| Selective Writer、精确重复、显式 revision / retraction | 已有 | 小幅扩展低风险等价判断与重复来源强化；高风险独立保存 |
| Finding、历史观察、未核实声明、冲突提示 | 已有 | 保持 Business DB 权威，不物理压缩历史 |
| 滚动摘要与两级注入 | 尚未实现 | 独立派生对象、源指针与版本；可失效、可重建 |
| 阈值异步治理与周期入口 | 尚未实现 | 持久化幂等队列与可重复执行 CLI；不假定部署存在 worker |
| 统一模型输入预算 | 尚未实现，仅分区字符/条数上限 | 所有实际 payload 的最终硬限，软配额、完整性检查与明确降级 |
| 管理员预算配置 | 尚未实现；现有 role 只允许 doctor | 预算策略接口与 UI 可独立实施，身份扩展方案需业务确认 |
| 旧 case memory 私有来源 | 旧记录不含 doctor 来源 | 不纳入新摘要；正常注入旧来源的处理需业务确认 |
| 真实 CT、Stable Lesion ID、多 worker、PostgreSQL | 不属于已验收范围 | 延后独立任务，不能从合成记忆验收推导上线能力 |

## 3. 本轮重跑的 V2.1 相关基线

相关回归：**340 passed、0 failed、2 warnings，84.72 秒**。范围为 memory/access/auth/business/entity、Agent 状态与工具、会话恢复、REST API、报告 Finding 输入与格式、CLI 与运行输出。该数字是相关测试集，不是完整仓库回归。

原 V2.1 报告中的 26 次模型调用、15 条公开回答、八类场景和 37 项检查是上一批证据，本轮真实模型验证另行记录，不复用为 V2.2 通过结论。

## 4. 计数与参数探索

保持现有方舟 `deepseek-v4.1-flash` 和 Coding Plan 地址。官方模型表的上下文容量与应用安全硬限分开设置，具体参数仍需 P1 比较；没有将旧对话中探索数字改成生产硬指标。

本轮合成 probe 验证：Coding Plan 路径的 tokenization 返回 404；同主机标准 `/api/v3/tokenization` 返回 200，可取得文本 BPE token 数。将实际 Chat payload 序列化为文本仍需 framing 余量，不能标作计费精确值。两个短 Chat 的官方 usage 分别为 13 和 52 输入 tokens；保守 UTF-8 全 payload 估算为 483 和 696，差异会在 P1 中明确展示。

源依据：[方舟 Coding Plan 官方文档](https://docs.volcengine.com/docs/ark/coding-plan-personal-ai-zcode?lang=zh)。本机合成 probe 证据位于被忽略的 `tmp/v22-model-probe/counts.json`，不保存密钥或原始服务错误。

## 5. 重要冲突的确认结果

实施前已向用户提出两项方案，不重新讨论 D1–D8；本轮用户均明确确认推荐方案：

1. 现有 doctor 身份增加默认关闭的 `budget_admin` 能力，由维护命令显式授予，复用 Cookie 认证且不授予额外患者访问权；另一选项是独立管理员账号类型。
2. 新 case memory 绑定医生；来源不明旧记录保留但停止正常 Prompt 注入，等待人工归属；另一选项是暂保留旧路径，仅禁止它进入新摘要。

答复前未实施对应的身份或旧记忆可见性变更；收到确认后才接入默认关闭的预算能力和旧来源阻断。合成测试会验证同一 Cookie 下授权/撤销立即生效，且患者权限不扩大。
