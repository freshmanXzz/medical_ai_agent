"""
DeepSeekClient - DeepSeek LLM 客户端
提供与DeepSeek API的接口
"""
import os
import json
import requests
from typing import List, Dict, Optional

class DeepSeekClient:
    """
    DeepSeek LLM 客户端
    
    Args:
        api_key: DeepSeek API密钥
        base_url: API基础URL
        model: 模型名称
    """
    
    def __init__(self, api_key: str = None, 
                 base_url: str = "https://api.deepseek.com/v1",
                 model: str = "deepseek-chat"):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.base_url = base_url
        self.model = model
        
        if not self.api_key:
            raise ValueError("API密钥未设置，请设置DEEPSEEK_API_KEY环境变量或传入api_key参数")
    
    def chat(self, messages: List[Dict[str, str]], 
            temperature: float = 0.7,
            max_tokens: int = 1024) -> str:
        """
        与DeepSeek模型对话
        
        Args:
            messages: 消息列表，格式: [{"role": "user", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大生成token数
        
        Returns:
            模型回复内容
        """
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()
        return result["choices"][0]["message"]["content"]
    
    def analyze_report(self, report_data: Dict) -> str:
        """
        分析医学报告数据
        
        Args:
            report_data: 报告数据字典
        
        Returns:
            分析结果
        """
        prompt = f"""
请分析以下肺部结节检测报告：

检测结果：
- 检测到结节数量: {report_data.get('total_nodules', 0)}

结节详情：
{json.dumps(report_data.get('nodules', []), indent=2, ensure_ascii=False)}

请提供专业的医学分析和建议，包括：
1. 结节的良恶性评估
2. 下一步建议（如随访、进一步检查等）
3. Lung-RADS分类建议
4. 患者注意事项
"""
        
        messages = [
            {"role": "system", "content": "你是一位专业的放射科医生，请用专业但易懂的语言分析医学报告。"},
            {"role": "user", "content": prompt}
        ]
        
        return self.chat(messages)
    
    def generate_report(self, nodules: List[Dict]) -> str:
        """
        生成医学报告
        
        Args:
            nodules: 结节检测结果列表
        
        Returns:
            格式化的医学报告
        """
        prompt = f"""
请根据以下肺部结节检测结果生成一份专业的医学报告：

结节数据：
{json.dumps(nodules, indent=2, ensure_ascii=False)}

报告格式要求：
1. 使用中文
2. 包含患者信息、检查方法、检测结果、诊断结论、建议等部分
3. 使用专业医学术语
4. 对每个结节进行评估
"""
        
        messages = [
            {"role": "system", "content": "你是一位专业的医学报告撰写专家，请生成格式规范的医学报告。"},
            {"role": "user", "content": prompt}
        ]
        
        return self.chat(messages)
    
    def summarize_findings(self, findings: List[Dict]) -> str:
        """
        总结检测发现
        
        Args:
            findings: 检测发现列表
        
        Returns:
            总结内容
        """
        prompt = f"""
请总结以下肺部结节检测发现：

检测发现：
{json.dumps(findings, indent=2, ensure_ascii=False)}

请用简洁明了的语言总结关键发现。
"""
        
        messages = [
            {"role": "system", "content": "请用简洁的语言总结医学检测结果。"},
            {"role": "user", "content": prompt}
        ]
        
        return self.chat(messages)
