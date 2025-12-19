import re

class ProgramManager:
    def __init__(self):
        self.program_list = []
        # 其他的话题回调标识，表示收到执行结束信号用于握手
    

# 提供单例实例（可选，保持原有使用习惯）
program_manager = ProgramManager()
# program_list = program_manager.program_list

def extract_params_to_dict(param_str):
    # 正则匹配 {} 内的所有内容
    pattern = r"\{(.*?)\}"
    values = re.findall(pattern, param_str)
    
    # 过滤空值（防止有 {} 空包裹的情况）
    values = [v.strip() for v in values if v.strip()]
    
    # 方案1：按顺序生成编号键（如 key1、key2...）
    result_dict = {f"{i+1}": val for i, val in enumerate(values)}
    
    return result_dict
