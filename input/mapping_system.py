"""
pairwise-input-mapping-system - InputMappingSystem

This module contains a deliberately broken implementation.
Fix all bugs so that tests pass.
"""


class InputMappingSystem:
    def __init__(self):
        self.state = {}

    def bind_action(self, *args, **kwargs):
        """BUG: 绑定动作不做冲突检测，两个动作绑同一个键"""
        return None

    def process_input(self, *args, **kwargs):
        """BUG: 输入处理不做映射，直接用原始按键"""
        return None

    def load_config(self, *args, **kwargs):
        """BUG: 配置加载不做版本检查，旧版本配置加载崩溃"""
        return None

    def get_key_hint(self, *args, **kwargs):
        """BUG: 按键提示不做本地化，不同语言显示一样"""
        return None

    def record_input(self, *args, **kwargs):
        """BUG: 输入录制不做时间戳，回放速度不对"""
        return None

