---
name: martin-vision-pipeline
description: 维护 Martin 的 CT 上传、MinIO 对象路径、NIfTI、MetaImage、DICOM 支持、MONAI 肺结节检测或检测结果数据契约时使用；适用于 martin/vision、影像 API 和集成测试修改。
---

# Martin Vision Pipeline

## 工作流

1. 先追踪文件从上传接口、对象存储到 `analyze_image` 和 `NoduleDetector` 的完整路径。
2. 明确区分本地临时路径、对象键和用户展示文件名；不要在跨平台界面或持久状态中写死盘符。
3. 修改检测结果字段时，同步检查 `CaseContext`、报告输入、前端 `DetectResult` 和历史会话恢复。

## 不可破坏的契约

- 仅把受支持的真实医学影像格式送入 MONAI；无文件、不可下载或模型缺失必须返回可诊断错误，不能虚构检测结果。
- 检测输出至少保留结节数量、尺寸、坐标、置信度及原始文件关联；字段变更必须兼容已保存病例或提供迁移路径。
- 不能把当前深色分析画布描述成真实 DICOM 阅片器；窗宽窗位、MPR 和标注仍是路线图能力。
- 大模型、原始影像和运行结果不纳入 Git 或测试夹具。

## 验证

默认运行不加载真实大模型的单元测试；真实 MONAI 推理保持单独集成测试。使用项目测试包装器和 `monai_learning` 环境，参考 `docs/ROADMAP.md`。
