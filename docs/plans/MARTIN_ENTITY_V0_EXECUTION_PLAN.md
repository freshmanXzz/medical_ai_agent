# MARTIN_ENTITY_V0_EXECUTION_PLAN.md

> 状态：**可实施计划**
>
> 适用仓库：`D:/agent_martin/medical_ai_agent`
>
> 当前分支：`refactor/memory-auth-v1`
>
> 当前解释器：`D:/agent_martin/conda/envs/medical_ai_agent/python.exe`
>
> 目标：先完成 Entity V0（身份 / 患者 / 病例 / Thread / 权限 / 最小业务事实），再进入 SqliteStore V1。
>
> 本计划继承以下已定稿约束：
>
> - `app.sqlite` = 业务事实源
> - `SqliteStore` = 跨 thread 长期记忆
> - `SqliteSaver` = thread/checkpoint 运行状态
> - 不建立 `app.sqlite.memories`
> - Store 读取前必须先做业务授权
> - 业务事实先写 Business DB，成功后再派生 Store
> - Store V1 只做确定性写入
> - Medical Observation 追加保存，不能让 8mm 覆盖 6mm
> - 当前不引入 PostgreSQL / PostgresSaver / PostgresStore / embedding / Mem0

---

# 1. 决策结论

## 决策 1：Entity V0 建哪些表？

**采纳“一次建齐 Demo A / Demo B 所需最小表”的方向，但把“业务表”和“基础设施表”分开命名。**

Entity V0 建：

### 8 张业务 / 实体表

```text
users
patients
cases
threads
doctor_patient_access
attachments
findings
reports
```

### 2 张基础设施 / 审计表

```text
auth_sessions
case_change_audit
```

总计：

```text
10 tables
```

原因：

1. `findings` 是患者纵向 CT Demo 的真实事实落点。
2. `attachments` 是影像与 Case 的归属落点。
3. `reports` 是报告版本的事实落点。
4. V1 采用服务端 Session，因此必须有 `auth_sessions`。
5. 接受增加 `case_change_audit`，用于 Phase 1 的 CaseChange / 后续实体修改审计。

明确：

```text
不建 memories 表
```

长期 Agent Memory 后续统一进入：

```text
SqliteStore
```

---

## 决策 2：`threads.id` 是否直接等于 LangGraph `thread_id`？

**接受合并。**

V1：

```text
threads.id == LangGraph configurable.thread_id
```

即同一个 UUID 同时作为：

```text
业务 Thread ID
LangGraph thread_id
```

原因：

```text
避免维护两个 1:1 标识
当前没有 thread 迁移 / 重编号需求
调用链更简单
```

但必须写死删除规则：

```text
业务 Thread 删除
↓
先删除 SqliteSaver 对应 checkpoint
↓
确认 checkpoint 删除成功或进入显式失败状态
↓
再删除 app.sqlite 的 threads 行
```

禁止：

```text
只删 threads 行
留下 sessions.sqlite 孤儿 checkpoint
```

`SqliteSaver` checkpoint 数据：

```text
不属于 app.sqlite 业务备份
不参与业务事实迁移
```

如果未来出现：

```text
thread ID 重编号
跨系统迁移
一个业务 thread 对应多个 LangGraph execution thread
```

再增加：

```text
threads.langgraph_thread_id
```

V1 不提前增加。

---

## 决策 3：doctor_id 如何获得？

**采用最小服务端 Auth，不做 Auth UI。**

V1 实现：

```text
POST /api/auth/login
username + password
↓
服务端校验
↓
创建 auth_sessions 记录
↓
返回 HttpOnly Cookie
```

所有需要业务身份的端点：

```python
Depends(get_current_doctor)
```

由服务端得到：

```text
doctor_id
```

禁止：

```text
从 request body 读取并信任 doctor_id
从 query param 读取并信任 doctor_id
从 prompt 文本推断 doctor_id
```

Entity V0 提供两个测试医生：

```text
D001
D002
```

注意：

```text
D001 / D002 仅用于 seed / fixture
正式创建的新用户仍使用 UUID
```

密码哈希：

```text
优先使用 Argon2id
```

实施 Agent 先检查仓库是否已有密码哈希依赖。

若没有：

```text
显式新增 argon2-cffi
```

不得存明文密码。

Session Token：

```text
客户端 Cookie 保存随机 opaque token
数据库只保存 token_hash
```

Cookie：

```text
HttpOnly = true
SameSite = Lax
Secure = 配置控制（生产必须 true）
```

本批不做 Auth UI。

---

## 决策 4：SqliteStore key 如何保证 Observation 不互相覆盖？

**按 Memory 类型固定 key 规则。**

虽然 Store V1 在 Entity V0 之后实施，但现在先冻结规则。

### Preference

```text
固定 key
```

示例：

```text
report_style
```

同一偏好：

```text
put 同 key → 更新
```

### Current State

```text
固定 key
```

示例：

```text
current_hospital
```

### Medical Observation

**禁止固定 key。**

Observation 必须使用业务事实 ID：

```text
observation:{finding_id}
```

示例：

```text
observation:8f7c...
observation:c381...
```

因此：

```text
2026-06 / 6mm
2026-09 / 8mm
```

对应两个不同 `finding_id`，Store 中天然并存。

不要用：

```text
"latest_ct"
"nodule_size"
```

这种固定 key 保存时间序列 Observation。

### Clinical Decision

建议：

```text
decision:{decision_type}:v{version}
```

value 中必须带：

```text
source_case_id
confirmed_by
confirmed_at
version
```

V1 测试必须证明：

```text
同一 patient 两个不同 finding_id
↓
Store 中两个 observation key 同时存在
```

---

# 2. Entity V0 SQLite DDL

建议新增：

```text
martin/db/schema.sql
```

DDL：

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('doctor')),
    password_hash   TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    token_hash      TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    last_seen_at    TEXT,
    revoked_at      TEXT,
    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user
    ON auth_sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_token_hash
    ON auth_sessions(token_hash);

CREATE TABLE IF NOT EXISTS patients (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    sex             TEXT CHECK (sex IN ('male', 'female', 'other', 'unknown') OR sex IS NULL),
    birth_date      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL,
    case_type       TEXT NOT NULL DEFAULT 'general',
    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'closed', 'archived')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (patient_id)
        REFERENCES patients(id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_cases_patient
    ON cases(patient_id);

CREATE TABLE IF NOT EXISTS threads (
    id              TEXT PRIMARY KEY,
    doctor_id       TEXT NOT NULL,
    case_id         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'closed', 'archived')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (doctor_id)
        REFERENCES users(id)
        ON DELETE RESTRICT,
    FOREIGN KEY (case_id)
        REFERENCES cases(id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_threads_doctor
    ON threads(doctor_id);

CREATE INDEX IF NOT EXISTS idx_threads_case
    ON threads(case_id);

CREATE TABLE IF NOT EXISTS doctor_patient_access (
    doctor_id       TEXT NOT NULL,
    patient_id      TEXT NOT NULL,
    access_level    TEXT NOT NULL DEFAULT 'read_write'
                    CHECK (access_level IN ('read_only', 'read_write')),
    created_at      TEXT NOT NULL,
    PRIMARY KEY (doctor_id, patient_id),
    FOREIGN KEY (doctor_id)
        REFERENCES users(id)
        ON DELETE CASCADE,
    FOREIGN KEY (patient_id)
        REFERENCES patients(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_access_patient
    ON doctor_patient_access(patient_id);

CREATE TABLE IF NOT EXISTS attachments (
    id              TEXT PRIMARY KEY,
    case_id         TEXT NOT NULL,
    uploaded_by     TEXT,
    original_name   TEXT NOT NULL,
    storage_path    TEXT NOT NULL,
    mime_type       TEXT,
    sha256          TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (case_id)
        REFERENCES cases(id)
        ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by)
        REFERENCES users(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_attachments_case
    ON attachments(case_id);

CREATE TABLE IF NOT EXISTS findings (
    id                  TEXT PRIMARY KEY,
    case_id             TEXT NOT NULL,
    source_attachment_id TEXT,
    created_by          TEXT,
    finding_type        TEXT NOT NULL,
    anatomy             TEXT,
    diameter_mm         REAL CHECK (diameter_mm IS NULL OR diameter_mm >= 0),
    observed_at         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'confirmed'
                        CHECK (status IN ('draft', 'confirmed', 'superseded')),
    payload_json        TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    FOREIGN KEY (case_id)
        REFERENCES cases(id)
        ON DELETE CASCADE,
    FOREIGN KEY (source_attachment_id)
        REFERENCES attachments(id)
        ON DELETE SET NULL,
    FOREIGN KEY (created_by)
        REFERENCES users(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_findings_case
    ON findings(case_id);

CREATE INDEX IF NOT EXISTS idx_findings_observed_at
    ON findings(observed_at);

CREATE TABLE IF NOT EXISTS reports (
    id              TEXT PRIMARY KEY,
    case_id         TEXT NOT NULL,
    created_by      TEXT,
    version         INTEGER NOT NULL CHECK (version >= 1),
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'final', 'superseded')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    finalized_at    TEXT,
    FOREIGN KEY (case_id)
        REFERENCES cases(id)
        ON DELETE CASCADE,
    FOREIGN KEY (created_by)
        REFERENCES users(id)
        ON DELETE SET NULL,
    UNIQUE (case_id, version)
);

CREATE INDEX IF NOT EXISTS idx_reports_case
    ON reports(case_id);

CREATE TABLE IF NOT EXISTS case_change_audit (
    id              TEXT PRIMARY KEY,
    actor_user_id   TEXT,
    target_type     TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    action          TEXT NOT NULL,
    before_json     TEXT,
    after_json      TEXT,
    occurred_at     TEXT NOT NULL,
    FOREIGN KEY (actor_user_id)
        REFERENCES users(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_case_change_target
    ON case_change_audit(target_type, target_id);

CREATE INDEX IF NOT EXISTS idx_case_change_actor
    ON case_change_audit(actor_user_id);
```

---

## 2.1 为什么 `threads.case_id` 使用 `ON DELETE RESTRICT`

因为：

```text
Thread row
```

与：

```text
SqliteSaver checkpoint
```

存在跨数据库生命周期关系。

如果 Case 删除时数据库自动 CASCADE 掉 Thread：

```text
应用层将失去同步清理 checkpoint 的机会
```

因此：

```text
Case hard delete
↓
先通过 ThreadService 删除全部 Thread + checkpoint
↓
再删除 Case
```

这比 DB 自动 CASCADE Thread 更安全。

---

## 2.2 PostgreSQL 迁移时要改的点

未来 PostgreSQL：

```text
TEXT UUID
→ UUID 类型

INTEGER 0/1
→ BOOLEAN

created_at / updated_at TEXT
→ TIMESTAMPTZ

SQLite PRAGMA
→ 删除

SQLite busy_timeout / WAL
→ 删除

INSERT OR IGNORE / SQLite upsert
→ PostgreSQL ON CONFLICT

SQLite connection handling
→ connection pool
```

业务接口：

```text
Repository / Service
```

尽量保持不变。

---

# 3. ID 规则与种子数据

## 3.1 正式 ID

所有正式实体：

```text
user_id
patient_id
case_id
thread_id
attachment_id
finding_id
report_id
audit_id
session_id
```

统一：

```python
uuid.uuid4()
```

输出字符串形式 UUID。

---

## 3.2 Thread ID

```text
threads.id
```

直接传给：

```python
config = {
    "configurable": {
        "thread_id": thread.id
    }
}
```

禁止：

```text
客户端任意提供一个不存在的 thread_id 然后直接运行 Agent
```

正确：

```text
POST /api/threads
↓
服务端生成 UUID
↓
写 app.sqlite
↓
返回 thread_id
↓
后续 Agent 调用验证其归属后使用
```

---

## 3.3 测试 Seed

提供两个测试医生：

```text
D001 / doctor_a
D002 / doctor_b
```

注意：

```text
D001 / D002 是 fixture 稳定 ID
只用于测试 / 本地开发 seed
```

示例：

```text
D001
username = doctor_a
password = TestDoctorA!2026

D002
username = doctor_b
password = TestDoctorB!2026
```

密码必须在 seed 时 hash。

测试患者：

```text
P001 = Patient Alpha
P002 = Patient Beta
```

访问关系：

```text
D001 → P001 = read_write
D002 → P002 = read_write
D002 → P001 = 无权限
```

测试病例：

```text
C001 → P001
C002 → P001
C003 → P002
```

用于纵向 CT：

```text
C001 / 2026-06 / finding F001 / RUL / 6mm
C002 / 2026-09 / finding F002 / RUL / 8mm
```

---

# 4. 级联 / 删除规则

| 删除对象 | 业务 DB 行为 | Saver / Store 行为 | 明确不做 |
|---|---|---|---|
| Auth Session | 只删该 session | 无 | 不删 User |
| User | V1 推荐停用 `is_active=0`；硬删时 auth_sessions/access CASCADE，存在 threads 时 RESTRICT | 后续清理 doctor Store namespace | 不自动删除 Patient |
| Patient | 如果存在 Case，RESTRICT；无 Case 时 access CASCADE | Store V1 后需清理 patient namespace + doctor-private patient namespace | 不靠 Store 判断能否删除 |
| Case | 必须先删除所有 Thread；然后 attachments/findings/reports CASCADE | Store V1 后清理 case namespace | 不自动删除 Patient |
| Thread | **应用层先删 Saver checkpoint，再删 threads 行** | 不影响 Patient/Case Store | 不删 Case |
| Attachment | findings.source_attachment_id → SET NULL | 无 | 不删 Finding |
| Finding | 只删事实行；正常场景优先 supersede/审计而非硬删 | Store V1 后清理对应 `observation:{finding_id}` | 不删 Case |
| Report | 删除指定版本；正常场景优先 supersede | 无 | 不删 Case |
| doctor_patient_access | 删除访问关系 | 立即阻止后续 Patient Store 读取 | 不删 Patient / Doctor |
| Audit | 原则上不级联删除；V1 无普通业务端点删除 audit | 无 | 不作为可编辑业务数据 |

---

## 4.1 Thread 删除的固定流程

```text
ThreadService.delete_thread(actor, thread_id)
↓
校验 thread 属于 actor 且 case 已授权
↓
调用 CheckpointService.delete_thread(thread_id)
↓
成功
↓
ThreadRepository.delete(thread_id)
↓
写 audit
```

如果 checkpoint 删除失败：

```text
V1：业务 thread 不删除
返回显式错误
```

避免：

```text
业务 thread 已不存在
但旧 checkpoint 仍可恢复
```

实施前 Agent 必须验证当前 `SqliteSaver` 版本提供的 thread 删除 API。

优先调用官方 saver API。

禁止默认直接手写 DELETE checkpoint 内部表。

---

# 5. 代码结构与确切文件清单

以下为本计划的目标文件结构。

如果现有仓库已有等价模块：

```text
复用现有结构
不要为了目录一致而无意义搬文件
```

---

## 5.1 新增

```text
martin/db/__init__.py
martin/db/app_db.py
martin/db/schema.sql

martin/repositories/__init__.py
martin/repositories/users.py
martin/repositories/auth_sessions.py
martin/repositories/patients.py
martin/repositories/cases.py
martin/repositories/threads.py
martin/repositories/access.py
martin/repositories/attachments.py
martin/repositories/findings.py
martin/repositories/reports.py
martin/repositories/audit.py

martin/auth/__init__.py
martin/auth/passwords.py
martin/auth/session_service.py

martin/services/__init__.py
martin/services/access_service.py
martin/services/thread_service.py
martin/services/case_service.py

api/deps/__init__.py
api/deps/auth.py

api/routers/auth.py
api/routers/patients.py
api/routers/cases.py
api/routers/threads.py

scripts/init_app_db.py
scripts/seed_entity_v0.py

tests/entity/conftest.py
tests/entity/test_schema.py
tests/entity/test_seed.py
tests/entity/test_repositories.py
tests/entity/test_cascade_rules.py
tests/auth/test_login.py
tests/auth/test_current_doctor.py
tests/auth/test_auth_sessions.py
tests/access/test_case_authorization.py
tests/access/test_patient_authorization.py
tests/access/test_thread_authorization.py
tests/business/test_findings.py
tests/business/test_reports.py
tests/business/test_attachments.py
tests/business/test_longitudinal_facts.py
tests/entity/test_entity_v0_acceptance.py

docs/refactor/ADR-001-entity-store-boundary.md
```

---

## 5.2 修改

```text
api/main.py
api/models.py
api/routers/agent.py

martin/agent/agent.py
martin/agent/sessions.py

scripts/run_tests.ps1
requirements.txt

D:/agent_martin/MEDICAL_AI_AGENT_REFACTOR_PLAN.md
```

注意：

```text
martin/agent/agent.py
martin/agent/sessions.py
```

只允许做 Entity V0 接线所需最小修改。

**不得破坏或重写 Phase 1 已完成的 F01/F02/F03 修复。**

---

# 6. 分批任务

规则：

```text
每批必须独立验收
当前批未通过
禁止进入下一批
```

测试入口：

```powershell
$env:MARTIN_TEST_PYTHON="D:/agent_martin/conda/envs/medical_ai_agent/python.exe"
```

如果现有 `scripts/run_tests.ps1` 不能透传 pytest 参数：

```text
Batch 0 仅做向后兼容的参数透传修复
```

建议目标：

```powershell
.\scripts\run_tests.ps1 tests/entity/test_schema.py -q
```

必须仍然由 `MARTIN_TEST_PYTHON` 选择解释器。

---

## Batch 0 — 决策落地 + superseded + Baseline

### 目标

```text
冻结 Entity V0 决策
冻结 Store / Business DB 边界
标记旧 memories 路线 superseded
确认测试 wrapper 可定向运行测试
确认 Phase 1 baseline 未被破坏
```

### 新增

```text
docs/refactor/ADR-001-entity-store-boundary.md
```

ADR 必须记录：

```text
app.sqlite = facts/auth/entities
SqliteStore = Agent long-term memory
SqliteSaver = thread state
no app.sqlite.memories
threads.id == LangGraph thread_id in V1
```

### 修改

```text
D:/agent_martin/MEDICAL_AI_AGENT_REFACTOR_PLAN.md
scripts/run_tests.ps1  # 仅当当前 wrapper 不能透传 pytest args 时
```

### superseded 动作

见第 7 节。

### 验收测试

```text
Phase 1 原有测试全部仍能运行
```

### 验收命令

```powershell
cd D:/agent_martin/medical_ai_agent
$env:MARTIN_TEST_PYTHON="D:/agent_martin/conda/envs/medical_ai_agent/python.exe"
.\scripts\run_tests.ps1
```

### 通过条件

```text
旧 Phase 1 测试结果不比修改前更差
ADR 存在
旧 memories 路线已明确标 superseded
```

---

## Batch 1 — DDL + 初始化 + Seed

### 目标

建立：

```text
app.sqlite
```

和 10 张 Entity V0 表。

### 新增 / 修改

```text
martin/db/__init__.py
martin/db/app_db.py
martin/db/schema.sql
scripts/init_app_db.py
scripts/seed_entity_v0.py
tests/entity/conftest.py
tests/entity/test_schema.py
tests/entity/test_seed.py
```

### `app_db.py` 职责

```text
获取 app.sqlite path
创建 connection
每个 connection 执行 PRAGMA foreign_keys=ON
init_schema()
transaction context manager
```

Repository 不自行决定数据库文件路径。

### 验收测试

```text
test_schema_is_idempotent
test_foreign_keys_are_enabled
test_expected_tables_exist
test_expected_indexes_exist
test_invalid_role_rejected
test_invalid_access_level_rejected
test_seed_contains_two_doctors
test_seed_access_matrix
```

### 验收命令

```powershell
cd D:/agent_martin/medical_ai_agent
$env:MARTIN_TEST_PYTHON="D:/agent_martin/conda/envs/medical_ai_agent/python.exe"
.\scripts\run_tests.ps1 tests/entity/test_schema.py tests/entity/test_seed.py -q
```

### 通过条件

```text
初始化脚本连续执行两次不报错
foreign_keys=ON
D001/D002/P001/P002/C001/C002/C003 正确 seed
无 memories 表
```

---

## Batch 2 — Repositories（纯 SQL）

### 目标

实现持久化 CRUD，但：

```text
Repository 不做授权判断
```

授权放 Service。

### 新增 / 修改

```text
martin/repositories/__init__.py
martin/repositories/users.py
martin/repositories/auth_sessions.py
martin/repositories/patients.py
martin/repositories/cases.py
martin/repositories/threads.py
martin/repositories/access.py
martin/repositories/attachments.py
martin/repositories/findings.py
martin/repositories/reports.py
martin/repositories/audit.py
tests/entity/test_repositories.py
tests/entity/test_cascade_rules.py
```

### Repository 最低接口

```text
UserRepository
- create
- get_by_id
- get_by_username
- deactivate

PatientRepository
- create
- get_by_id

CaseRepository
- create
- get_by_id
- list_by_patient

ThreadRepository
- create
- get_by_id
- list_by_case
- delete

AccessRepository
- grant
- revoke
- get_access

FindingRepository
- create
- get_by_id
- list_by_case
- list_by_patient

AttachmentRepository
- create
- get_by_id
- list_by_case

ReportRepository
- create_version
- list_by_case
- get_latest

AuditRepository
- append
- list_for_target
```

注意：

```text
Repository 可有 get_by_id
Service 层禁止暴露无 actor 的业务读取接口
```

### 验收测试

```text
test_repository_crud
test_patient_delete_restricted_when_cases_exist
test_case_delete_restricted_when_threads_exist
test_access_deleted_when_relationship_revoked
test_attachment_delete_sets_finding_source_null
test_report_case_version_unique
```

### 验收命令

```powershell
cd D:/agent_martin/medical_ai_agent
$env:MARTIN_TEST_PYTHON="D:/agent_martin/conda/envs/medical_ai_agent/python.exe"
.\scripts\run_tests.ps1 tests/entity/test_repositories.py tests/entity/test_cascade_rules.py -q
```

---

## Batch 3 — 最小 Auth + 服务端 doctor_id + Thread 创建

### 目标

实现：

```text
login
HttpOnly session cookie
get_current_doctor
服务端生成 thread_id
Agent 请求不能自报 doctor_id
```

### 新增 / 修改

```text
martin/auth/__init__.py
martin/auth/passwords.py
martin/auth/session_service.py
martin/repositories/auth_sessions.py
api/deps/__init__.py
api/deps/auth.py
api/routers/auth.py
api/routers/threads.py
api/main.py
api/models.py
api/routers/agent.py
requirements.txt
tests/auth/test_login.py
tests/auth/test_current_doctor.py
tests/auth/test_auth_sessions.py
tests/access/test_thread_authorization.py
```

### API

```text
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me

POST /api/threads
```

Thread 创建：

```text
current doctor
+
authorized case
↓
server uuid
↓
threads row
↓
return thread_id
```

Agent endpoint：

```text
必须要求已有合法 thread
```

禁止：

```text
请求 body 任意构造 doctor_id
请求 body 任意构造未登记 thread_id
```

### Session

Cookie 中：

```text
raw opaque token
```

DB：

```text
SHA-256 token hash
```

密码：

```text
Argon2id hash
```

### 验收测试

```text
test_login_sets_httponly_cookie
test_invalid_password_rejected
test_request_without_cookie_is_401
test_current_doctor_comes_from_server_session
test_body_doctor_id_is_ignored_or_rejected
test_logout_revokes_session
test_server_creates_thread_uuid
test_arbitrary_thread_id_cannot_be_used
```

### 验收命令

```powershell
cd D:/agent_martin/medical_ai_agent
$env:MARTIN_TEST_PYTHON="D:/agent_martin/conda/envs/medical_ai_agent/python.exe"
.\scripts\run_tests.ps1 tests/auth tests/access/test_thread_authorization.py -q
```

---

## Batch 4 — Authorization Service

### 目标

所有 Patient / Case / Thread 读取：

```text
必须带 actor
```

Service 层不允许：

```python
get_case(case_id)
```

只允许：

```python
get_case_authorized(doctor_id, case_id)
```

同理：

```python
get_patient_authorized(...)
get_thread_authorized(...)
```

### 新增 / 修改

```text
martin/services/access_service.py
martin/services/case_service.py
martin/services/thread_service.py
api/routers/patients.py
api/routers/cases.py
api/routers/threads.py
api/routers/agent.py
tests/access/test_case_authorization.py
tests/access/test_patient_authorization.py
tests/access/test_thread_authorization.py
```

### 固定规则

```text
Case → Patient
↓
doctor_patient_access
↓
authorized
```

Thread：

```text
thread.doctor_id 必须等于 current doctor
并且 current doctor 对 thread.case.patient 有访问权
```

### 越权测试

```text
D002 无 P001 权限
↓
GET /case/C001
→ 403

D002 手工改 URL 中 case_id
→ 403

D002 使用 D001 的 thread_id 调 Agent
→ 403
```

### 验收命令

```powershell
cd D:/agent_martin/medical_ai_agent
$env:MARTIN_TEST_PYTHON="D:/agent_martin/conda/envs/medical_ai_agent/python.exe"
.\scripts\run_tests.ps1 tests/access -q
```

---

## Batch 5 — Findings / Attachments / Reports + Demo B 前置事实链路

### 目标

让：

```text
患者
↓
Case
↓
Attachment
↓
Finding
↓
Report
```

形成最小真实业务事实链。

### 新增 / 修改

```text
martin/repositories/attachments.py
martin/repositories/findings.py
martin/repositories/reports.py
api/routers/cases.py
api/models.py
martin/agent/tools.py
tests/business/test_findings.py
tests/business/test_reports.py
tests/business/test_attachments.py
tests/business/test_longitudinal_facts.py
```

只做最小接线。

不要在本批引入 Store。

### CT 事实

必须能表达：

```text
P001
├── C001
│   └── F001 / 2026-06 / RUL / 6mm
└── C002
    └── F002 / 2026-09 / RUL / 8mm
```

### 验收测试

```text
test_confirmed_finding_persisted
test_findings_queryable_by_case
test_findings_queryable_by_patient
test_two_observations_do_not_overwrite
test_attachment_belongs_to_case
test_report_versions_are_preserved
```

### 验收命令

```powershell
cd D:/agent_martin/medical_ai_agent
$env:MARTIN_TEST_PYTHON="D:/agent_martin/conda/envs/medical_ai_agent/python.exe"
.\scripts\run_tests.ps1 tests/business -q
```

### 通过条件

数据库能够稳定查询：

```text
P001 历史 finding：
6mm
8mm
```

两条并存。

---

## Batch 6 — Thread / Checkpoint 生命周期 + Entity V0 总验收

### 目标

完成：

```text
Business Thread
↔
SqliteSaver checkpoint
```

生命周期规则。

### 新增 / 修改

```text
martin/services/thread_service.py
martin/agent/sessions.py
api/routers/threads.py
tests/entity/test_entity_v0_acceptance.py
tests/access/test_thread_authorization.py
```

### 删除测试

创建：

```text
Thread
↓
产生 checkpoint
↓
调用 ThreadService.delete_thread
```

验证：

```text
threads row 不存在
checkpoint 也不存在
```

如果 checkpointer 删除失败：

```text
threads row 必须仍存在
```

### Entity V0 验收项目

```text
[ ] user/doctor 有稳定 ID
[ ] patient 有稳定 ID
[ ] case 有稳定 ID
[ ] thread 有稳定 ID
[ ] Case → Patient 正确
[ ] Thread → Case / Doctor 正确
[ ] doctor_patient_access 正确
[ ] doctor_id 来源于 server session
[ ] 不使用 thread_id 冒充 patient_id
[ ] 不使用 patient name 当 patient_id
[ ] 未授权 Case / Thread 请求返回 403
[ ] P001 可有多个 Case
[ ] 6mm / 8mm Finding 并存
[ ] 删除 Thread 同步删除 checkpoint
[ ] app.sqlite 不存在 memories 表
[ ] Phase 1 原有测试没有回归
```

### 验收命令

```powershell
cd D:/agent_martin/medical_ai_agent
$env:MARTIN_TEST_PYTHON="D:/agent_martin/conda/envs/medical_ai_agent/python.exe"
.\scripts\run_tests.ps1 tests/entity/test_entity_v0_acceptance.py tests/entity tests/auth tests/access tests/business -q
```

然后跑完整回归：

```powershell
cd D:/agent_martin/medical_ai_agent
$env:MARTIN_TEST_PYTHON="D:/agent_martin/conda/envs/medical_ai_agent/python.exe"
.\scripts\run_tests.ps1
```

Entity V0 全绿后：

```text
才能进入 SqliteStore V1
```

---

# 7. `superseded` 动作

目标文件：

```text
D:/agent_martin/MEDICAL_AI_AGENT_REFACTOR_PLAN.md
```

旧计划中所有：

```text
app.sqlite.memories
自建 memories 表
以 scope + subject_id 作为 Agent 长期记忆主体
要求 memories 与业务事实同事务
```

全部标记：

```text
SUPERSEDED — 2026-09-28
```

新的统一决策：

```text
Business DB
= 实体、权限、事实

SqliteStore
= Agent 长期记忆

SqliteSaver
= Thread 状态
```

建议在旧计划开头加入：

```markdown
> ## Architecture Override — 2026-09-28
>
> 原计划中以 `app.sqlite.memories` 作为 Agent 长期记忆主体的路线已被替代。
>
> 当前统一方案：
>
> - `app.sqlite`：业务实体、权限、真实事实
> - `SqliteStore`：跨 thread 长期 Agent Memory
> - `SqliteSaver`：LangGraph thread/checkpoint 状态
>
> 不再新增 `app.sqlite.memories`。
> 旧文中涉及 `memories` 表、memory 与业务事实同事务的内容仅保留为历史设计记录，不再实施。
```

对旧文件中此前定位的相关条目：

```text
约第 63
69
364
375
641
745 行附近
```

增加：

```text
> SUPERSEDED: See Architecture Override 2026-09-28.
```

不要删除旧内容。

保留历史设计轨迹。

同时新增：

```text
docs/refactor/ADR-001-entity-store-boundary.md
```

作为仓库内正式决策记录。

---

# 8. 风险与不做清单

## 8.1 当前风险

### 风险 A：Phase 1 尚未完全验证

Entity V0 开工前：

```text
必须先跑 Phase 1 baseline
```

不得把 Entity 改造掩盖成 Phase 1 修复。

---

### 风险 B：Thread 删除跨两个 SQLite

`threads` 在：

```text
app.sqlite
```

checkpoint 在：

```text
sessions.sqlite
```

无法共享事务。

V1 规则：

```text
先删 checkpoint
成功后删 business thread
```

失败显式返回。

---

### 风险 C：Auth 与业务权限不是同一件事

```text
登录成功
≠
可以看所有 Patient
```

必须：

```text
Auth
+
doctor_patient_access
```

两层都过。

---

### 风险 D：Store 以后仍然是派生层

进入 Store V1 后也必须保持：

```text
Finding / Report / Patient / Case
不能只存在 Store
```

Store 丢失应可从业务库重建。

---

### 风险 E：SQLite 并发能力有限

当前：

```text
本地 / 单机 / V1
```

接受 SQLite。

出现：

```text
多 worker
高并发写
远程部署
多个服务实例
```

再进入 PostgreSQL 演进。

---

## 8.2 本批明确不做

```text
PostgreSQL
PostgresSaver
PostgresStore

app.sqlite.memories

Store V1 具体实现
Memory embedding
BGE
向量检索
Semantic Memory
Mem0
TTL
Memory consolidation

Auth UI
OAuth
SSO
复杂 RBAC
组织 / 科室权限
患者共享审批流

完整医疗 EMR schema
DICOM PACS 集成
复杂报告审批系统

多 worker 并发优化
分布式事务
消息队列 / outbox
```

---

# 9. Entity V0 完成后的下一步

只有 Batch 0–6 全部通过后：

```text
Entity V0
↓
SqliteStore V1
```

此时 Store 可安全使用：

```python
("doctor", doctor_id, "preferences")

("doctor", doctor_id, "patient", patient_id, "private")

("patient", patient_id, "memory")

("case", case_id, "memory")
```

因为：

```text
doctor_id
patient_id
case_id
```

已经是业务系统中的稳定实体 ID。

然后按 Store V1 计划实施：

```text
Demo A
医生偏好跨 thread

Demo B
患者纵向 CT 跨 thread
```

---

# 10. 实施 Agent 的停止条件

任何一批出现以下情况：

```text
测试失败
schema 与现有代码冲突
需要改写 Phase 1 F01/F02/F03
需要引入本计划外大型依赖
需要改变三层职责边界
需要重新引入 app.sqlite.memories
```

必须：

```text
停止
记录问题
报告差异
等待决策
```

禁止自行扩大范围。

---

# 11. 最终定义

```text
Business DB
负责：
身份
患者
病例
Thread 归属
权限
附件
Finding
Report
审计
真实事实

SqliteStore
负责：
医生偏好
患者长期记忆
病例长期记忆
跨 thread Recall

SqliteSaver
负责：
Messages
Graph State
Tool State
Checkpoint
Thread Resume
```

Entity V0 的任务不是“做长期记忆”。

Entity V0 的任务是：

> **给长期记忆建立可靠的“谁 / 哪个患者 / 哪个病例”坐标系。**

完成后，SqliteStore 才能真正安全地作为 Martin 的长期记忆层。
