# validation_scripts — 可复跑的验收与探针脚本

来源：从工作区 `validation/` 收编入库（2026-09-30，按 AGENT_HANDOFF_PROTOCOL.md 第二节第 2 条）。**以后新验收脚本一律放这里**，不再放仓库外。

## 脚本清单

| 脚本 | 用途 | 判定标准 | 产物位置 |
| --- | --- | --- | --- |
| `store_v1_live_acceptance.py` | SqliteStore V1 真实模型三场景验收（A 医生偏好 / B 纵向对比 / C 故障降级），真实 REST + 隔离合成库 | `evidence.json → checks`；A: 8 项结构检查含 `at_most_200_chars`（**全字符口径**，2026-09-30 Martin 裁定）；B/C 结构过 + 语义复核 | `../validation/store-v1-live-<时间戳>/`（仓库外） |
| `store_v11_live_acceptance.py` | V1.1 扩展变体（A 三线程 / C REST+WS），复用上一脚本作 harness | 同上口径 | 同上 |
| `ark_model_smoke.py` | LLM 连通性冒烟（读 conda state 凭据，发一次真实调用） | checks 全 true | `../validation/ark-model-smoke.json` |
| `record_environment.py` | 记录 Python/包/SQLite 版本基线 | 输出即证据 | 脚本同目录 `environment.json` |

## 运行假设

- 路径均由 `__file__` 推导（`parents[2]` = 工作区根），**无硬编码盘符**；
- LLM 凭据从 `<工作区根>/conda/envs/medical_ai_agent/conda-meta/state` 的 `env_vars` 读取（`DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`）——换机器时保持该位置或改脚本头部；
- live 脚本自建隔离三库（`RUN` 目录），不触碰 `data/` 正式库；验收服务监听 8001，结束自动关闭；
- 凭据只从本地文件读，脚本内不含任何密钥。

## 复跑示例（SqliteStore V1 定验）

```bash
cd <工作区根>
conda/envs/medical_ai_agent/python.exe medical_ai_agent/validation_scripts/store_v1_live_acceptance.py
# 结束后看 stdout 的 Evidence 路径，checks 里三场景 PASS/FAIL
```

注意：跑前确认没有别的进程占用 8001；8000 常驻服务不是必要条件（健康检查已非致命化，2026-09-30）。
