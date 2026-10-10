# 历史记忆 Prompt 基线

`memory_v21/router.py` 是 V2.2 实施前保存的原 V2.1 `martin/memory/router.py`，仅用于合成 P1 Prompt 投影对照。它不是当前运行模块，也不是完整旧 Agent 重放。

该文件从 2026-10-09 的源码快照提取，原始 SHA256 为 `02578724d02f674efdc35435b373aba454f53e882bbb4edececf55033ee70b4d`；`manifest.json` 保留基线分支和当时 HEAD，并明确该 HEAD 只是工作区基底，不等于已验收 V2.1 源码。加载时核验原始字节 SHA256。目录内 `.gitattributes` 禁止对此文件转换换行，以保证跨机器拉取后哈希一致。

夹具只包含这一个源文件及来源元数据，不包含运行库、患者资料、配置、凭据或整份快照。

从仓库根、已选择的项目 Python 环境复跑：

```powershell
python validation_scripts/memory_v22_quality_baseline.py --output-dir tmp/v22-p1-recheck
```

指标逻辑与原验收相同；输入计数是 UTF-8 上界估计，时延是本机渲染测量，不能当作模型计费或生产 SLA。`memory_v22_live_acceptance.py` 的 P1 配对使用同一个核验入口，仍需本地配置模型凭据与服务。
