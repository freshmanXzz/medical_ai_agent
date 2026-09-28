"""Exceptions shared by agent execution and transport adapters."""


class CasePersistenceError(RuntimeError):
    """病例状态未能持久化，调用方必须返回失败。"""
