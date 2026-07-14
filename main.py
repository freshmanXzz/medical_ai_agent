"""Martin Medical Agent — 根目录入口

使用方式:
    python main.py                   → 启动 Agent 对话模式
    python -m martin <command> ...   → 完整子命令（detect / case / agent / ...）

本文件将 python main.py 委托给 martin/__main__.py 的 handle_agent_v2()。
"""

if __name__ == "__main__":
    from martin.__main__ import handle_agent_v2
    from argparse import Namespace

    handle_agent_v2(Namespace(image=None, report_type="detailed", language="zh"))
