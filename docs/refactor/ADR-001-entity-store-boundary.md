# ADR-001：业务实体与 Agent 状态的存储边界

状态：已决定；Entity V0 尚未建表或接线。日期：2026-09-28。

## 背景

当前 Martin 以 LangGraph checkpoint 保存会话消息和 `CaseContext`。它不能独立表达医生身份、患者、病例、授权和跨会话的医学事实。Entity V0 先给这些对象稳定的 ID 与归属，长期记忆随后才能安全引用它们。

## 决策

| 存储 | 职责 | 不承担 |
|---|---|---|
| `data/app.sqlite` | 用户、登录会话、患者、病例、Thread 归属、授权、附件、Finding、报告、审计等业务事实 | Agent 长期记忆表 |
| LangGraph `SqliteStore` | 已获授权主体的跨 Thread Agent 记忆；优先从业务事实确定性派生 | 病例事实源和权限源 |
| LangGraph `SqliteSaver` / `data/sessions.sqlite` | Thread 消息、Graph State、工具状态与 checkpoint | 患者和病例的永久业务身份 |

`app.sqlite` 不建立 `memories` 表。事实先写业务库，成功后才派生 Store 内容；Store 读取前先由业务库验证医生对患者/病例的授权。医学 Observation 以事实 ID 生成 `observation:{finding_id}`，不同时间的 6mm 与 8mm Finding 并存，不覆盖旧观察。

Entity V0 首批为八张业务/实体表 `users`、`patients`、`cases`、`threads`、`doctor_patient_access`、`attachments`、`findings`、`reports`，另有 `auth_sessions`、`case_change_audit` 两张基础设施/审计表。Auth 使用服务端 Session 和 HttpOnly Cookie；`doctor_id` 只能从服务端身份取得。这个表清单是目标，不表示本 ADR 创建了表。

V1 中 `threads.id` 与 LangGraph `configurable.thread_id` 为同一 UUID。删除 Thread 时先清除并确认 SqliteSaver checkpoint，再删除业务 Thread；checkpoint 清除失败时保留业务行并显式报错。Case 删除受 Thread 外键限制，先完成各 Thread 生命周期处理。

Store V1 使用确定性写入。医生 Preference / Current State 可以用固定 key；医学 Observation 必须用 Finding ID 区分版本。当前不引入 PostgreSQL、嵌入式记忆检索或独立记忆表。

## 影响与实施门槛

Entity V0 由独立批次实现并验收。现有 Phase 1 状态修复和接口回归必须先核对；本文不改变运行时代码。旧重构计划中以 `app.sqlite.memories`、`scope + subject_id` 自建表为长期记忆主体的段落保留作历史记录，但由本决策取代。
