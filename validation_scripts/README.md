# validation_scripts — 可复跑的验收与探针脚本

来源：从工作区 `validation/` 收编入库（2026-09-30，按 AGENT_HANDOFF_PROTOCOL.md 第二节第 2 条）。**以后新验收脚本一律放这里**，不再放仓库外。

## 脚本清单

| 脚本 | 用途 | 判定标准 | 产物位置 |
| --- | --- | --- | --- |
| `store_v1_live_acceptance.py` | SqliteStore V1 真实模型三场景验收（A 医生偏好 / B 纵向对比 / C 故障降级），真实 REST + 隔离合成库 | `evidence.json → checks`；A: 8 项结构检查含 `at_most_200_chars`（**全字符口径**，2026-09-30 Martin 裁定）；B/C 结构过 + 语义复核 | `../validation/store-v1-live-<时间戳>/`（仓库外） |
| `store_v11_live_acceptance.py` | V1.1 扩展变体（A 三线程 / B 真实 6mm→8mm / C REST+WS+当前分析），复用上一脚本作 harness | 同上口径；B/C 必须复核公开回答语义 | 同上 |
| `memory_architecture_live_acceptance.py` | 三检索扩展：真实 Agent 保存显式决策，跨 Thread 组合 Exact/Temporal/Semantic；REST+WS、无权医生与语义索引故障 | `checks`；结构成功后仍需公开回答语义复核，不冒充临床或 CT 验收 | 同上；附 `manifest.json` |
| `finding_report_live_acceptance.py` | V1.1-1 当前病例 Finding → 三类报告 REST + Agent 工具，无 CT，隔离合成三库 | `checks`：业务读取、真实报告 Prompt、真实模型回答含部位/日期/8mm、不混入历史 6mm；另需语义复核无虚构 | `../validation/finding-report-live-<时间戳>/`（仓库外） |
| `ark_model_smoke.py` | LLM 连通性冒烟（读 conda state 凭据，发一次真实调用） | checks 全 true | `../validation/ark-model-smoke.json` |
| `record_environment.py` | 记录 Python/包/SQLite 版本基线 | 输出即证据 | 脚本同目录 `environment.json` |

## 运行假设

- Store V1/V1.1 的仓库路径由 `__file__.parents[1]` 推导，工作区为仓库父目录；支持不同仓库名称和跨机位置；
- Store V1/V1.1 凭据优先使用环境变量，其次读取仓库 `.env`（`DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`）。缺配置时明确退出，不依赖某台机器的 Conda state；
- Store live 脚本自建隔离三库和空知识 Chroma（`RUN` 目录），不触碰正式患者数据或知识文档；默认保留系统分配的空闲本地端口，可用 `MARTIN_ACCEPTANCE_PORT` 显式指定，结束自动关闭；
- 凭据只从本地环境或配置文件读取，脚本内不含任何密钥。
- 其他脚本仍保留其各自配置方式（下述报告回填脚本有旧 Conda state 回退）；不能据此推定它们均已跨机验证。

## 复跑示例（SqliteStore V1 定验）

```bash
cd <仓库根>
# 先激活所选项目环境，或将 python 换成已选择的项目解释器
python validation_scripts/store_v11_live_acceptance.py
# 三检索架构集成后运行
python validation_scripts/memory_architecture_live_acceptance.py
# 结束后看 stdout 的 Evidence 路径；FAIL 或运行异常退出码为 1
# REVIEW 表示结构检查通过，B/C 的公开回答仍需语义复核
```

注意：若显式指定端口，跑前确认该端口空闲；8000 常驻服务不是必要条件（健康检查已非致命化，2026-09-30）。Store 验收只用合成种子数据，证据保留实际模型输入和公开回答，剥离 reasoning 和凭据字段；不验证真实 CT/MONAI 推理。

每次 Store 验收的 `manifest.json` 记录合成 seed 范围和三库、知识库、对象目录的隔离位置。影像分析、上传、下载工具被验收 guard 阻止，若模型意外调用会记入证据并失败；该 guard 不模拟影像成功。模型接收应用系统 Prompt 与合成数据，需现有模型服务配置及网络访问授权。

V1.1-1 报告回填验收：在仓库根目录，用项目解释器运行
`validation_scripts/finding_report_live_acceptance.py`。优先读取已配置的三个
`DEEPSEEK_*` 环境变量；不齐时使用上述本机 Conda state。脚本自启隔离 API，
结束即停；不会改正式业务库。仅生成基础报告，不要求 MONAI 权重或 CT 影像。
