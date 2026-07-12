"""LangChain 文档加载器封装模块

支持多种格式文档的加载：
- Markdown (.md)
- CSV (.csv)
- PDF (.pdf)
- Word (.docx)

提供目录遍历加载和基于配置的知识库加载功能。
"""

import warnings
from pathlib import Path
from typing import List

import yaml
from langchain_community.document_loaders import (
    CSVLoader,
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document

from martin.config import config

# 支持的文件扩展名到加载器的映射
LOADER_MAP = {
    ".md": TextLoader,
    ".csv": CSVLoader,
    ".pdf": PyPDFLoader,
    ".docx": Docx2txtLoader,
}

# 支持的扩展名集合
SUPPORTED_EXTENSIONS = set(LOADER_MAP.keys())


def _get_loader(file_path: str):
    """根据文件扩展名返回对应的文档加载器实例。

    Args:
        file_path: 文件路径

    Returns:
        加载器实例；如果不支持该扩展名，返回 None
    """
    ext = Path(file_path).suffix.lower()
    loader_class = LOADER_MAP.get(ext)
    if loader_class is None:
        return None
    return loader_class(file_path)


def load_knowledge_directory(dir_path: str) -> List[Document]:
    """遍历指定目录，加载所有支持的文档文件。

    按文件扩展名自动选择对应的加载器：
      - .md  → TextLoader
      - .csv → CSVLoader
      - .pdf → PyPDFLoader
      - .docx → Docx2txtLoader

    单个文件加载失败不影响其他文件的加载，失败信息通过 warnings.warn() 输出。

    Args:
        dir_path: 要遍历的目录路径

    Returns:
        所有成功加载的 Document 列表，每个 Document 的 metadata 中包含 source 字段
    """
    directory = Path(dir_path)
    if not directory.exists() or not directory.is_dir():
        warnings.warn(f"目录不存在或不是有效目录: {dir_path}")
        return []

    documents: List[Document] = []
    for file_path in sorted(directory.iterdir()):
        if not file_path.is_file():
            continue
        ext = file_path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        try:
            loader = _get_loader(str(file_path))
            if loader is None:
                continue
            docs = loader.load()
            for doc in docs:
                doc.metadata["source"] = file_path.name
            documents.extend(docs)
        except Exception as e:
            warnings.warn(f"加载文件失败 [{file_path.name}]: {e}")
            continue

    return documents


def load_knowledge_base() -> List[Document]:
    """从配置文件中读取知识库文档列表，加载所有文档并添加分类信息。

    配置来源：configs/knowledge_base.yaml
    - 从 knowledge_base.directory 字段读取文档存放目录
    - 从 knowledge_base.documents 列表读取每个文档的 filename 和 category
    - 为每个 Document 的 metadata 添加 category（分类）字段

    Returns:
        所有加载完成的 Document 列表
    """
    # 读取知识库配置文件
    config_path = config.project_root / "configs" / "knowledge_base.yaml"
    if not config_path.exists():
        warnings.warn(f"知识库配置文件不存在: {config_path}")
        return []

    with open(config_path, "r", encoding="utf-8") as f:
        kb_config = yaml.safe_load(f)

    if not kb_config or "knowledge_base" not in kb_config:
        warnings.warn("知识库配置文件格式错误：缺少 knowledge_base 字段")
        return []

    kb = kb_config["knowledge_base"]
    kb_dir = config.project_root / kb.get("directory", "knowledge_base")
    documents_config = kb.get("documents", [])

    if not documents_config:
        warnings.warn("知识库配置中未定义任何文档")
        return []

    all_documents: List[Document] = []
    for doc_entry in documents_config:
        filename = doc_entry.get("filename")
        category = doc_entry.get("category", "unknown")

        if not filename:
            warnings.warn("知识库配置中存在缺少 filename 的文档条目")
            continue

        file_path = kb_dir / filename
        if not file_path.exists():
            warnings.warn(f"知识库文档不存在: {file_path}")
            continue

        try:
            loader = _get_loader(str(file_path))
            if loader is None:
                warnings.warn(f"不支持的文档格式: {file_path.suffix} ({filename})")
                continue
            docs = loader.load()
            for doc in docs:
                doc.metadata["source"] = filename
                doc.metadata["category"] = category
            all_documents.extend(docs)
        except Exception as e:
            warnings.warn(f"加载知识库文档失败 [{filename}]: {e}")
            continue

    return all_documents
