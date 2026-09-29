# SqliteStore V1 阶段入口

日期：2026-09-29。状态：核心离线回归已通过；真实模型验收已运行，A FAIL / B PASS / C FAIL，**SqliteStore V1 = NOT ACCEPTED**。详情见 [真实模型验收记录](SQLITESTORE_V1_LIVE_ACCEPTANCE.md)。以下早期记录保留为阶段历史。

## 前置核对

- Entity V0 已验收：最终全量 229 passed、1 skipped、0 failed、0 errors。
- 已安装的 LangGraph 版本提供 `langgraph.store.sqlite.SqliteStore`；独立临时 SQLite 文件的 `setup/put/get` 探针通过。
- app.sqlite 已有稳定的 doctor/patient/case/thread ID 和服务端授权关系；SqliteSaver 继续管理 Thread checkpoint。

## 已修改

- `martin/memory/store.py` 集中管理独立 `data/memory.sqlite` 的打开、初始化与关闭；该数据库及伴随文件被 Git 忽略。
- `martin/memory/namespaces.py` 统一四类 namespace；`martin/memory/service.py` 在业务库授权后读写医生偏好、医生私人患者笔记、病例记忆，并从已确认的 Finding 确定性写入 `observation:{finding_id}`。
- 未更改 RAG、app.sqlite schema、Agent Prompt 或既有业务事实。

## 已运行 / 已测试 / 已通过

- 真实 SqliteStore 基础层测试 5 passed：覆盖重开恢复、D001/D002 偏好隔离、6mm 与 8mm Observation 并存、未授权访问拒绝，以及两名医生均可访问同一患者时私人 namespace 仍隔离。
- 纳入基础层后的全量回归：234 passed、1 skipped、0 failed、0 errors；日志：`D:/agent_martin/validation/store-v1-entry-full-20260929.log`。

## 尚未验证

- 真实外部 LLM 是否稳定遵守报告风格与纵向比较指令；真实医学推理不能由脚本模型代替。
- 因此本记录表示 V1 核心代码与离线集成验收通过，**不表示真实模型场景已验收**。

## 2026-09-29 增量验证

### 已修改

- 已授权的 Agent 请求从业务 Thread 推导医生、患者、病例 ID；当前病例 Finding 与患者历史 Store 观察分区进入同轮 Prompt，记忆内容不写入 Saver checkpoint。
- 明确的长期报告偏好可由 Agent 工具或登录医生专用接口写入；工具的 actor ID 由服务端提供，模型参数不能指定医生 ID。
- 从业务库的 confirmed Finding 确定性重建 Store 观察；`observation:{finding_id}` 保留不同时间点，superseded Finding 会从 Store 投影清除。
- Store 读取失败时保留当前病例事实；明确要求历史比较的 REST/WS 请求返回“历史记忆不可用，无法可靠比较”。偏好写入失败时 REST/WS 不返回“已保存”成功。

### 已运行 / 已测试 / 已通过

- 使用真实 SqliteSaver + SqliteStore + app.sqlite、脚本模型及合成 Finding 的 Demo A/B、跨医生隔离、Store 读写故障、REST/WS 错误路径：`tests/memory/test_store_v1_integration.py` 6 passed。
- 首次全量回归 238 passed、2 failed、1 skipped；两个新失败为旧状态测试绕过 Agent 构造函数而缺少新属性。已在 Agent 入口为未设置 V1 属性的实例使用空上下文，不修改旧状态测试。
- 修复后状态回归与 V1 专项：16 passed；最终完整回归：**240 passed、1 skipped、0 failed、0 errors**。日志：`D:/agent_martin/validation/store-v1-full-final-20260929.log`。

## 2026-09-29 真实模型验收

- 已加载新模型配置并启动正常服务；健康检查通过。验收使用独立合成 SQLite 与真实 HTTP / LLM，结束后关闭验收服务。
- Doctor Preference：FAIL。偏好成功保存、跨 Thread 检索并进入实际模型输入；最终报告 487 字符（324 个汉字），结论未在开头。失败表现在指令遵循，Prompt 对偏好的约束优先级需要完善；另发现报告链空值格式化及失败状态识别问题。
- Longitudinal Memory：PASS。历史 6mm、当前 8mm、+2mm 均正确，实际 Prompt 来源分区与最终回答无混用。
- Store Failure Degradation：FAIL。故障被检测，但 API 在模型执行前直接返回 503；没有 Prompt 注入或最终 LLM 回答，不能以接口提示替代 live acceptance。
- 三层证据和失败归因已记录；最小 V1 回归 11 passed。未修改生产代码、RAG 或依赖，不进入 V2。
