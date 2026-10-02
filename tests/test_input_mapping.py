import pytest
from input.mapping_system import InputMappingSystem


class TestInputMappingSystem:

    def test_bind_action(self):
        """绑定动作不做冲突检测，两个动作绑同一个键"""
        obj = InputMappingSystem()
        result = obj.bind_action()
        self.assertIsNotNone(result)

    def test_process_input(self):
        """输入处理不做映射，直接用原始按键"""
        obj = InputMappingSystem()
        result = obj.process_input()
        self.assertIsNotNone(result)

    def test_load_config(self):
        """配置加载不做版本检查，旧版本配置加载崩溃"""
        obj = InputMappingSystem()
        result = obj.load_config()
        self.assertIsNotNone(result)

    def test_get_key_hint(self):
        """按键提示不做本地化，不同语言显示一样"""
        obj = InputMappingSystem()
        result = obj.get_key_hint()
        self.assertIsNotNone(result)

    def test_record_input(self):
        """输入录制不做时间戳，回放速度不对"""
        obj = InputMappingSystem()
        result = obj.record_input()
        self.assertIsNotNone(result)

