# V1.1-1：报告生成接业务 Finding 回填

日期：2026-09-30。范围仅为 ROADMAP 近期第 1 项，不启动其余 V1.1 待办或 V2。

## 已修改

- 新增只读 `ReportInputService`。以服务端医生身份和 Thread 反查当前病例，
  在同一业务库事务内授权并读取 `confirmed / nodule` Finding；不读 Store，
  不写业务库，也不查询患者历史病例来填当前报告。
- Finding 独立重建报告结节：业务列 `anatomy / observed_at / diameter_mm`
  为准；该 Finding 的 payload 只补检测置信度、坐标和三维尺寸。不会把模型
  检测列表与业务列表按位置拼接；没有检测字段就保留缺失，不补零。
- Agent 调用和报告 REST 入口共用服务端报告 scope，调用后必定还原。
  报告 REST 要求登录及 `session_id`，仅使用服务端 checkpoint 和业务事实；
  请求中的 `detection_result / case_context` 保留字段兼容，但不作为事实源。
- 三种报告的实际 Prompt 和模板降级均回填解剖部位、直径及逐结节观察日期。
  观察日期与报告生成日期分开；业务 Finding 不被描述为本轮新完成 CT 检测。
- 已有业务记录但没有可用已确认结节时，旧 checkpoint 不会使失效值复活；
  没有业务 Finding 的旧会话继续兼容服务端检测快照，包括已完成零结节检测。
  无事实且未检测时明确资料不足，不报“未检测到结节”。REST chat 的浏览器
  结节投影不会覆盖服务端检测事实。
- 报告页面传入真实 Thread，解除必须先做 CT 检测的门槛。默认病例选择未改，
  患者/病例发现仍属于 ROADMAP 第 4 项。CLI 独立检测 JSON 契约继续兼容。
- 新增可复跑 `validation_scripts/finding_report_live_acceptance.py`，使用隔离
  合成三库和自启/自停验收 API，记录业务读取 → 实际模型 Prompt → 最终回答。

## 已运行 / 已测试

Python 与本机测试方式见 `AGENT.md / LOCAL_NOTES.md`；所有 pytest 均使用
项目解释器和项目内 `--basetemp`，未安装或升级依赖。

| 范围 | 实际结果 |
| --- | --- |
| 修改前完整基线 | 280 passed / 1 skipped / 0 failed |
| 既有 Agent 工具、状态、Web、报告缺失测量核心测试 | 50 passed / 0 failed |
| 新格式测试 + 既有报告/LCEL 测试 | 51 passed / 1 skipped / 0 failed |
| Finding 输入、授权、工具、REST、真实 SQLite restart 测试 | 37 passed / 0 failed |
| 最终完整回归 | 329 passed / 1 skipped / 0 failed；146 条原有 warnings |
| 前端类型检查与生产构建 | PASS；保留原有 bundle 大小警告 |
| 真实模型 Finding 字段验收 | REST brief / detailed / research、Agent report：均 8/8 PASS |

本机证据位于工作区 `validation/`：`finding-v11-1-baseline-20260930.log`、
`finding-v11-1-core-20260930.log`、`finding-v11-1-format-20260930.log`、
`finding-v11-1-final-20260930.log`、
`finding-v11-1-frontend-build-20260930.log`、
`finding-v11-1-live-20260930.log`、
`finding-report-live-20260930-154814/evidence.json`。日志及 SQLite 不入 Git；
换机器按 validation_scripts/README.md 复跑。

## 已通过

- 当前病例 C002 的 F002（RUL、2026-09-01、8mm）进入真实报告模型 Prompt，
  并出现在四条 live 最终回答中。历史 F001 的 6mm 没有回填或混作当前值。
- 三层证据中业务读取仅含 F002，实际报告 Prompt 有三个业务字段；真实模型
  被调用并返回内容。成功模板回退不算 live 模型通过。
- 合成无 CT 病例的缺失置信度、坐标、形态未被补零或虚构；日期未替换为生成日期。
- 跨医生拒绝、撤权、缺失 Thread、业务 DB 失败不使用旧数据假成功；报告范围
  与 CaseContext 在异常后还原。三个真实 SQLite 重开场景保留恢复行为。
- 两处来源防护均有回归：过滤后的旧结节不复活，浏览器 99mm 不替换服务端事实。
- `answer_length` 全字符口径、confirmed 默认状态、业务库 → Store 单向投影、
  私人备注/病例记忆无模型写入口，以及既有纵向记忆逻辑均未变。

## 尚未验证 / 独立观察

- 本轮 live 验收只评价 Finding 字段链路。科研版一次真实回答末尾停在缺失信息
  清单，没有完整输出其余结构及 JSON；结构完整性不能写为通过。原因尚未定位，
  本轮未改变模型参数，也未扩大到报告质量的独立修复。
- 未重做完整浏览器点击流程、真实 CT/MONAI/MinIO 全链路，未做知识库上传重建。
  前端构建和真实报告 REST 已验证，不代替这些后续验收。
- 未重跑 SqliteStore V1 的 A/B/C live 定验；其已有 ACCEPTED 结论保留，相关
  离线回归本轮通过。其余 ROADMAP 项和 V2 仍待安排。

本项字段回填完成，阶段报告供 Martin 审阅；下一项范围按协作决策模式确认。
