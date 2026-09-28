# CaseContext 到 Entity V0 的字段映射

状态：Batch 5 实施约定；Batch 1–4 尚未将旧 checkpoint 自动迁入业务库。日期：2026-09-28。

`CaseContext` 是一个 Thread 的运行状态。只有经过当前医生授权、能关联到稳定 Patient/Case/Attachment ID，且来源明确的字段才能写成业务事实。旧 checkpoint 中缺少这些 ID 的内容保留为历史会话状态，不凭姓名或任意 `thread_id` 自动归并患者。

| CaseContext 字段 | Entity V0 落点与转换 | 约束 |
|---|---|---|
| `patient_info.age` | `cases.age_at_encounter_years` 与 `cases.age_recorded_at` | 年龄是某时点的陈述，**不反推精确 `patients.birth_date`**。仅已知准确出生日期时写 `birth_date`。年龄范围 0–130。 |
| `patient_info.gender` | `patients.sex` | `男/男性 → male`、`女/女性 → female`；未知/其他明确映射为 `unknown/other`，未识别值拒绝，不写入不合法枚举。 |
| `patient_info.smoking_history` | `cases.smoking_history` | 保留原始临床表述；修改由服务端审计。 |
| `patient_info.family_history` | `cases.family_history` | 同上，不从未提及推断“无”。 |
| `clinical_notes` | `cases.clinical_notes_json` | 保存有序字符串数组；追加需授权并记录审计，不能把审计表当唯一事实源。 |
| `image_info.object_name/filename` | `attachments.storage_path/original_name` | 仅服务端确认的 MinIO 对象；客户端传入路径不可信。附件必须属于已授权 Case。 |
| `detection_completed` | `attachments.analyzed_at` | 完成且无结节时仍写时间；未完成为 NULL。新的影像分析结果与附件关联。 |
| `nodules[]` | 每个结节一行 `findings` | `diameter` → `diameter_mm`；已证实的部位 → `anatomy`；score/center/dimensions 等模型细节进入 **`findings.payload_json`**，引用 `source_attachment_id`。不同时间/Case 的观察用不同 Finding ID，不能覆盖。交接文档中的 `attachments.payload_json` 在 Batch 1 DDL 中不存在，此处按实际 schema 更正。 |
| `knowledge_summary` | 仍在 checkpoint | 检索摘要是当轮 Agent 状态，不当成已确认医疗事实；后续 Store 也只能在授权与来源核实后派生。 |
| 报告生成结果 | `reports` 新版本 | 仅在明确的 Case 与已授权医生下创建；旧自由文本输出不自动写成正式报告。 |
| `created_at/updated_at` | 仍在 checkpoint | Entity 各行使用自己的时间戳，不复制 Thread 状态时间。 |

Batch 5 需给 `cases` 增加年龄/吸烟史/家族史/备注字段，给 `attachments` 增加 `analyzed_at`；通过幂等迁移兼容 Batch 1 已初始化的 `app.sqlite`，并补齐字段转换与空结节检测测试。迁移前不能声称这些字段已有业务落点。
