"""病例上下文管理模块。

提供 ``CaseContext`` 类，用于在同一会话内保存结构化的医学病例状态，
支持从检测结果、自然语言文本中更新上下文，并生成适合注入 LLM 的摘要字符串。
"""

import os
import re
from datetime import datetime, timezone
from typing import Any


class CaseContext:
    """医学病例上下文，保存患者信息、影像信息、结节、知识摘要与临床备注。"""

    # 患者信息字段白名单，确保不会引入无关键值
    PATIENT_INFO_KEYS = {"age", "gender", "smoking_history", "family_history"}

    def __init__(self) -> None:
        """初始化病例上下文，所有字段使用空默认值，并记录创建与更新时间。"""
        self.patient_info: dict[str, Any] = {
            "age": None,
            "gender": None,
            "smoking_history": None,
            "family_history": None,
        }
        self.image_info: dict[str, Any] = {
            "modality": "胸部CT",
            "image_path": None,
            "image_name": None,
            # 仅保存服务端可解析的对象引用；前端阅片接口不会接收路径或对象键。
            "source_type": None,
            "object_name": None,
            "filename": None,
        }
        self.nodules: list[dict[str, Any]] = []
        # ``nodules == []`` 既可能表示“尚未检测”，也可能表示“检测完成但未发现
        # 结节”。独立保存完成状态，供恢复历史会话和生成报告时准确区分两种情况。
        self.detection_completed: bool = False
        self.knowledge_summary: str = ""
        self.clinical_notes: list[str] = []
        self.created_at: str = self._now_iso()
        self.updated_at: str = self.created_at

    @staticmethod
    def _now_iso() -> str:
        """返回当前 UTC 时间的 ISO 格式字符串。"""
        return datetime.now(timezone.utc).isoformat()

    def _touch(self) -> None:
        """更新最后修改时间为当前时间。"""
        self.updated_at = self._now_iso()

    def update_from_detection(self, detection_result: dict) -> None:
        """从检测结果字典中填充影像信息与结节列表。

        Args:
            detection_result: 检测结果字典，包含 ``image``、``total_nodules``、
                ``nodules`` 等字段。
        """
        image_raw = detection_result.get("image")
        # 分析时使用的下载临时路径不能覆盖上传接口保存的稳定对象引用。
        if self.image_info.get("source_type") == "minio_object" and self.image_info.get("object_name"):
            self.image_info["image_path"] = self.image_info["object_name"]
            if not self.image_info.get("image_name"):
                self.image_info["image_name"] = os.path.basename(image_raw) if image_raw else None
        else:
            self.image_info["image_path"] = image_raw
            self.image_info["image_name"] = os.path.basename(image_raw) if image_raw else None

        # 若检测结果包含结节列表则保存，否则重置为空列表
        raw_nodules = detection_result.get("nodules")
        self.nodules = list(raw_nodules) if raw_nodules else []
        self.detection_completed = True

        self._touch()

    def set_image_source(self, object_name: str, filename: str | None = None) -> None:
        """保存当前病例可恢复的 MinIO 影像来源。

        ``image_path`` 保留为兼容报告和旧调用方的字段，但其值也只保留对象键，
        不记录服务端临时路径或用户设备路径。
        """
        if not isinstance(object_name, str) or not object_name.startswith("ct/"):
            return
        self.image_info.update(
            {
                "source_type": "minio_object",
                "object_name": object_name,
                "image_path": object_name,
                "image_name": filename or self.image_info.get("image_name"),
                "filename": filename or self.image_info.get("filename"),
            }
        )
        # 新上传文件不能继续展示上一病例的检测结果。
        self.nodules = []
        self.detection_completed = False
        self._touch()

    def to_public_dict(self) -> dict[str, Any]:
        """返回可发送到浏览器的病例上下文，不含服务端影像引用。"""
        data = self.to_dict()
        image_info = data.get("image_info")
        if isinstance(image_info, dict):
            for key in ("object_name", "image_path", "source_type"):
                image_info.pop(key, None)
        return data

    def update_patient_info(self, updates: dict) -> None:
        """更新患者信息字段，仅更新已存在的键。

        Args:
            updates: 需要更新的患者信息字典。
        """
        if not isinstance(updates, dict):
            return

        for key, value in updates.items():
            if key in self.PATIENT_INFO_KEYS:
                self.patient_info[key] = value

        self._touch()

    def add_clinical_note(self, note: str) -> None:
        """追加一条临床备注。

        Args:
            note: 非空备注字符串。
        """
        if isinstance(note, str) and note.strip():
            self.clinical_notes.append(note.strip())
            self._touch()

    def set_knowledge_summary(self, summary: str) -> None:
        """设置最近一次知识库检索结果摘要。

        Args:
            summary: 知识摘要字符串。
        """
        self.knowledge_summary = summary if isinstance(summary, str) else ""
        self._touch()

    @staticmethod
    def extract_patient_info(text: str) -> dict[str, Any]:
        """从自然语言文本中抽取患者信息。

        仅返回成功抽取的字段，未提及的字段不返回，避免覆盖已有值。

        Args:
            text: 自然语言文本。

        Returns:
            抽取到的患者信息字典，可能包含 ``age``、``gender``、
            ``smoking_history``、``family_history``。
        """
        if not isinstance(text, str) or not text.strip():
            return {}

        result: dict[str, Any] = {}

        # 抽取年龄：支持 "(<num>)岁"、"年龄(<num>)"、"年龄=(<num>)" 等格式
        age_patterns = [
            r"年龄\s*[:：=≤<]?\s*(\d+)",
            r"(\d+)\s*岁",
        ]
        for pattern in age_patterns:
            age_match = re.search(pattern, text)
            if age_match:
                result["age"] = int(age_match.group(1))
                break

        # 抽取性别：支持 "男"、"男性"、"女"、"女性"
        gender_match = re.search(r"(男|女)(?:性)?", text)
        if gender_match:
            result["gender"] = "男" if gender_match.group(1) == "男" else "女"

        # 抽取吸烟史：支持多种常见表述
        smoking_patterns = [
            r"(\d+)\s*年\s*吸\s*烟\s*史",
            r"吸\s*烟\s*(\d+)\s*年",
            r"(\d+)\s*包\s*年",
            r"有\s*吸\s*烟\s*史",
            r"无\s*吸\s*烟\s*史",
        ]
        for pattern in smoking_patterns:
            smoking_match = re.search(pattern, text)
            if smoking_match:
                if smoking_match.lastindex:
                    # 匹配到数字，构造描述性字符串
                    if "包年" in pattern:
                        result["smoking_history"] = f"{smoking_match.group(1)} 包年"
                    else:
                        result["smoking_history"] = f"吸烟 {smoking_match.group(1)} 年"
                else:
                    result["smoking_history"] = smoking_match.group(0)
                break

        # 抽取家族史：匹配 "有/无...家族史" 结构
        family_match = re.search(r"(有|无)\s*([\u4e00-\u9fa5]*?)\s*家族史", text)
        if family_match:
            result["family_history"] = family_match.group(0)

        return result

    def to_dict(self) -> dict[str, Any]:
        """返回病例上下文的完整字典表示，便于序列化。"""
        return {
            "patient_info": dict(self.patient_info),
            "image_info": dict(self.image_info),
            "nodules": list(self.nodules),
            "detection_completed": self.detection_completed,
            "knowledge_summary": self.knowledge_summary,
            "clinical_notes": list(self.clinical_notes),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CaseContext":
        """从字典恢复 ``CaseContext`` 实例。

        Args:
            data: 由 ``to_dict`` 生成的字典。

        Returns:
            恢复后的 ``CaseContext`` 实例。
        """
        instance = cls()
        instance.patient_info.update(data.get("patient_info", {}))
        instance.image_info.update(data.get("image_info", {}))
        instance.nodules = list(data.get("nodules", []))
        # 旧 checkpoint 没有该字段。已存在结节时可可靠地判定检测完成；
        # 空结节的旧数据无法区分“未检测”和“检测无结节”，保持为未检测以免
        # 生成缺少检测依据的报告。新写入的 checkpoint 均会携带明确状态。
        instance.detection_completed = bool(
            data.get("detection_completed", bool(instance.nodules))
        )
        instance.knowledge_summary = data.get("knowledge_summary", "")
        instance.clinical_notes = list(data.get("clinical_notes", []))
        instance.created_at = data.get("created_at", instance.created_at)
        instance.updated_at = data.get("updated_at", instance.updated_at)
        return instance

    def to_context_string(self, max_nodules: int = 5) -> str:
        """生成适合注入 LLM 的病例上下文摘要字符串。

        Args:
            max_nodules: 最多输出的结节数量，默认为 5。

        Returns:
            病例上下文摘要字符串；若上下文完全为空则返回空字符串。
        """
        if self.is_empty():
            return ""

        lines: list[str] = []

        # 患者信息段落：仅输出非空字段
        patient_items = []
        if self.patient_info.get("age") is not None:
            patient_items.append(f"年龄：{self.patient_info['age']} 岁")
        if self.patient_info.get("gender"):
            patient_items.append(f"性别：{self.patient_info['gender']}")
        if self.patient_info.get("smoking_history"):
            patient_items.append(f"吸烟史：{self.patient_info['smoking_history']}")
        if self.patient_info.get("family_history"):
            patient_items.append(f"家族史：{self.patient_info['family_history']}")

        if patient_items:
            lines.append("【患者信息】")
            lines.extend(patient_items)
            lines.append("")

        # 影像信息段落
        lines.append("【影像信息】")
        lines.append(f" modality：{self.image_info.get('modality', '胸部CT')}")
        display_name = self.image_info.get("filename") or self.image_info.get("image_name")
        if display_name:
            lines.append(f" 影像名称：{display_name}")
        lines.append("")

        # 结节摘要段落
        lines.append("【结节摘要】")
        lines.append(f" 结节总数：{len(self.nodules)}")
        displayed = self.nodules[:max_nodules]
        for idx, nodule in enumerate(displayed, start=1):
            info_parts = []
            for key in ("index", "diameter", "score", "center", "dimensions"):
                if key in nodule:
                    info_parts.append(f"{key}={nodule[key]}")
            info_str = ", ".join(info_parts) if info_parts else str(nodule)
            lines.append(f" 结节 {idx}：{info_str}")
        if len(self.nodules) > max_nodules:
            lines.append(f" ... 还有 {len(self.nodules) - max_nodules} 个结节未显示")
        lines.append("")

        # 最近一次检索知识摘要
        if self.knowledge_summary:
            lines.append("【知识摘要】")
            lines.append(self.knowledge_summary)
            lines.append("")

        # 临床备注
        if self.clinical_notes:
            lines.append("【临床备注】")
            for note in self.clinical_notes:
                lines.append(f"- {note}")
            lines.append("")

        return "\n".join(lines).strip()

    def is_empty(self) -> bool:
        """判断病例上下文是否为空。

        当患者信息全为空、无影像路径、无结节、无知识摘要且无临床备注时返回 True。
        """
        has_patient = any(value is not None and value != "" for value in self.patient_info.values())
        has_image = bool(self.image_info.get("image_path")) or bool(self.image_info.get("image_name"))
        has_nodules = bool(self.nodules)
        has_knowledge = bool(self.knowledge_summary)
        has_notes = bool(self.clinical_notes)
        return not (has_patient or has_image or has_nodules or has_knowledge or has_notes)
