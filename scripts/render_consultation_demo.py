"""Render the README consultation image with the production CLI UI."""

from io import StringIO
from pathlib import Path
import sys

from rich.console import Console
from rich.terminal_theme import MONOKAI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from martin.agent.cli_ui import AgentCLI


def main() -> None:
    console = Console(
        file=StringIO(),
        record=True,
        width=112,
        color_system="truecolor",
        force_terminal=True,
    )
    ui = AgentCLI(console)

    ui.welcome("demo-62m-ct")
    ui.user_message("最近咳嗽，体检 CT 还说有肺结节，想帮我看看。")
    ui.assistant(
        "可以。我是医学影像 AI，分析结果需要医生结合原始影像复核。\n\n"
        "先了解三个关键信息：患者年龄和性别？是否吸烟？CT 文件路径是什么？"
    )
    ui.user_message(
        "62 岁男性，吸烟 30 年，每天约一包，没有肺癌家族史。\n"
        "CT 在 E:\\data\\patient_001.nii.gz，之前没有做过 CT。"
    )
    ui.assistant(
        "已记录患者信息并完成影像分析。模型检测到 3 个结节：\n\n"
        "| 结节 | 位置 | 最大径 | 置信度 |\n"
        "|---|---|---:|---:|\n"
        "| 1 | 右上叶 | 8.2 mm | 98.5% |\n"
        "| 2 | 左下叶 | 5.0 mm | 96.1% |\n"
        "| 3 | 右下叶 | 3.8 mm | 91.7% |\n\n"
        "最大的 8.2 mm 结节需要重点评估。咳嗽持续多久？是否有咯血、胸痛或明显气促？"
    )
    ui.user_message("咳嗽两周，没有咯血和胸痛。请结合指南解释风险，再生成完整病例。")
    ui.assistant(
        "# 肺部 CT 智能辅助病例摘要\n\n"
        "- **患者信息：** 62 岁男性，吸烟 30 包年，肺癌家族史阴性。\n"
        "- **主诉：** 咳嗽 2 周，无咯血、胸痛及明显气促。\n"
        "- **影像发现：** 模型检出 3 个肺结节，最大结节位于右上叶，直径 8.2 mm。\n"
        "- **风险提示：** 年龄及长期吸烟史提高基线风险，需结合薄层 CT 形态进一步分级。\n"
        "- **建议：** 由放射科或呼吸科医生复核原始影像，并依据最终分级制定后续方案。\n\n"
        "> 本摘要由 AI 生成，仅用于辅助分析，不能替代临床诊断。",
        is_report=True,
    )

    output_path = PROJECT_ROOT / "docs" / "clinical_consultation_demo.svg"
    console.save_svg(
        str(output_path),
        title="Martin Medical AI Agent - 模拟问诊病例",
        theme=MONOKAI,
    )
    print(output_path)


if __name__ == "__main__":
    main()
