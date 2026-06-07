"""
测试LLM模块
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from martin.llm import DeepSeekClient

class TestDeepSeekClient(unittest.TestCase):
    """测试DeepSeek客户端"""
    
    def test_client_initialization_with_api_key(self):
        """测试客户端初始化（使用API密钥）"""
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        
        if api_key:
            client = DeepSeekClient(api_key=api_key)
            self.assertEqual(client.api_key, api_key)
            print("✓ 客户端初始化成功")
        else:
            print("⚠️  客户端测试跳过（未设置API密钥）")
    
    def test_client_initialization_no_api_key(self):
        """测试无API密钥时的错误处理"""
        original_key = os.environ.get("DEEPSEEK_API_KEY")
        
        if original_key:
            del os.environ["DEEPSEEK_API_KEY"]
        
        with self.assertRaises(ValueError):
            DeepSeekClient()
        
        if original_key:
            os.environ["DEEPSEEK_API_KEY"] = original_key
        
        print("✓ 无API密钥错误处理测试通过")
    
    def test_chat_method_exists(self):
        """测试聊天方法存在"""
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        
        if api_key:
            client = DeepSeekClient(api_key=api_key)
            self.assertTrue(hasattr(client, 'chat'))
            print("✓ 聊天方法存在")
        else:
            print("⚠️  聊天方法测试跳过（未设置API密钥）")

if __name__ == "__main__":
    unittest.main(verbosity=2)
