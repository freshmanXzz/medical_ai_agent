"""
Retriever - 检索器
整合向量数据库和Embedding模型，实现医学知识检索
"""
import json
from typing import List, Dict, Optional

# 导入统一日志工具
from martin.util import AppLogger

logger = AppLogger.setup_logging(__name__)

# 常量定义
DEFAULT_TOP_K = 5
DEFAULT_SIMILARITY_THRESHOLD = 0.7


class Retriever:
    """
    检索器
    
    整合Embedding客户端和向量数据库，实现医学知识检索
    
    Args:
        embedding_client: Embedding客户端实例
        vector_store: 向量数据库实例
        top_k: 返回结果数量
        similarity_threshold: 相似度阈值
    """
    
    def __init__(self, embedding_client, vector_store, top_k: int = DEFAULT_TOP_K, threshold: float = DEFAULT_SIMILARITY_THRESHOLD):
        """初始化检索器"""
        self.embedding_client = embedding_client
        self.vector_store = vector_store
        self.top_k = top_k
        self.similarity_threshold = threshold
        logger.info(f"Retriever 初始化完成: top_k={top_k}, threshold={threshold}")
    
    def search(self, query: str, category: str = None) -> List[Dict]:
        """
        检索相关知识
        
        Args:
            query: 查询文本
            category: 过滤分类
        
        Returns:
            检索结果列表
        """
        if not query:
            logger.warning("查询文本为空")
            return []
        
        logger.info(f"开始检索: query='{query}', category={category}")
        
        # 向量化查询文本
        query_embedding = self.embedding_client.encode_single(query)
        
        # 转换为列表格式供向量数据库使用
        query_embedding_list = query_embedding.tolist()
        
        # 执行相似度检索
        results = self.vector_store.similarity_search(
            query_embedding=query_embedding_list,
            top_k=self.top_k,
            category=category
        )
        
        # 过滤低于阈值的结果
        filtered_results = [
            result for result in results 
            if result.get("similarity", 0) >= self.similarity_threshold
        ]
        
        logger.info(f"检索完成: 原始结果 {len(results)} 条, 过滤后 {len(filtered_results)} 条")
        
        return filtered_results
    
    def search_by_detection(self, detection_result: Dict) -> List[Dict]:
        """
        根据检测结果检索相关知识
        
        Args:
            detection_result: 检测结果字典（包含nodules, total_nodules等）
        
        Returns:
            检索结果列表（Lung-RADS分级、诊断标准、随访建议等）
        """
        if not detection_result or not detection_result.get("nodules"):
            logger.warning("检测结果为空")
            return []
        
        # 构建查询文本
        query = self._build_query_from_detection(detection_result)
        logger.info(f"从检测结果构建查询: {query}")
        
        # 执行检索
        results = self.search(query)
        
        # 如果有多个结节，增加针对最大结节的检索
        nodules = detection_result.get("nodules", [])
        if len(nodules) > 0:
            # 找到最大的结节
            max_nodule = max(nodules, key=lambda n: n.get("diameter", 0))
            max_diameter = max_nodule.get("diameter", 0)
            
            # 添加针对大结节的检索
            size_query = f"肺部结节直径{max_diameter:.1f}mm 大小分级 处理建议"
            size_results = self.search(size_query)
            results.extend(size_results)
            
            # 去重
            results = self._deduplicate_results(results)
        
        return results
    
    def _build_query_from_detection(self, detection_result: Dict) -> str:
        """
        从检测结果构建检索查询
        
        Args:
            detection_result: 检测结果字典
        
        Returns:
            查询文本
        """
        total_nodules = detection_result.get("total_nodules", 0)
        nodules = detection_result.get("nodules", [])
        
        if total_nodules == 0:
            return "肺部CT检查未见结节 正常报告解读"
        
        # 获取结节统计信息
        diameters = [n.get("diameter", 0) for n in nodules]
        max_diameter = max(diameters) if diameters else 0
        avg_diameter = sum(diameters) / len(diameters) if diameters else 0
        min_diameter = min(diameters) if diameters else 0
        
        # 构建查询文本
        query_parts = []
        
        # 结节数量
        if total_nodules == 1:
            query_parts.append(f"单个肺部结节")
        elif total_nodules <= 3:
            query_parts.append(f"{total_nodules}个肺部结节")
        else:
            query_parts.append(f"多发肺部结节（{total_nodules}个）")
        
        # 结节大小描述
        size_descriptions = []
        if max_diameter > 0:
            if max_diameter < 6:
                size_descriptions.append("微小结节")
            elif max_diameter < 8:
                size_descriptions.append("小结节")
            elif max_diameter < 15:
                size_descriptions.append("中等大小结节")
            else:
                size_descriptions.append("大结节")
        
        if size_descriptions:
            query_parts.append(" ".join(size_descriptions))
        
        # 直径信息
        if max_diameter > 0:
            query_parts.append(f"最大直径{max_diameter:.1f}mm")
        
        # 添加检索目标
        query_parts.append("Lung-RADS分级 诊断标准 随访建议")
        
        return " ".join(query_parts)
    
    def _deduplicate_results(self, results: List[Dict]) -> List[Dict]:
        """
        对检索结果去重
        
        Args:
            results: 检索结果列表
        
        Returns:
            去重后的结果列表
        """
        seen_contents = set()
        unique_results = []
        
        for result in results:
            content = result.get("content", "")
            if content not in seen_contents:
                seen_contents.add(content)
                unique_results.append(result)
        
        # 按相似度排序
        unique_results.sort(key=lambda r: r.get("similarity", 0), reverse=True)
        
        # 限制返回数量
        return unique_results[:self.top_k]
    
    def _format_results(self, results: List[Dict]) -> str:
        """
        格式化检索结果为上下文文本
        
        Args:
            results: 检索结果列表
        
        Returns:
            格式化的上下文文本
        """
        if not results:
            return "未检索到相关医学知识。"
        
        context_parts = []
        for i, result in enumerate(results, 1):
            content = result.get("content", "")
            source = result.get("source", "")
            similarity = result.get("similarity", 0)
            
            part = f"【参考资料{i}】\n"
            part += f"内容：{content}\n"
            if source:
                part += f"来源：{source}\n"
            part += f"相似度：{similarity:.2f}\n"
            part += "---\n"
            
            context_parts.append(part)
        
        return "\n".join(context_parts)