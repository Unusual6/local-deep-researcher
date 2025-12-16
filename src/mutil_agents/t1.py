import re

# 原始数据（模拟你的 data 结构）
data = {
    "params": {
        "params": '{测试}{10.20}{1}{20251020}{20251021test}{20251021test-LD}{全布局}{20251022}{1022-50uL Antibody}{1022-LD}{20251028test1}{20251028查询残留}{20251028残留测试}{20251028-LD}'
    }
}

# 步骤1：提取所有 {} 内的内容
def extract_params_to_dict(param_str):
    # 正则匹配 {} 内的所有内容
    pattern = r"\{(.*?)\}"
    values = re.findall(pattern, param_str)
    
    # 过滤空值（防止有 {} 空包裹的情况）
    values = [v.strip() for v in values if v.strip()]
    
    # 方案1：按顺序生成编号键（如 key1、key2...）
    result_dict = {f"{i+1}": val for i, val in enumerate(values)}
    
    # 方案2：自定义业务键（如果知道每个值的含义，优先用这个）
    # 示例：根据业务含义命名（需你根据实际场景调整）
    # custom_keys = [
    #     "测试标识", "版本号", "序号", "日期1", "测试名称1", "LD标识1",
    #     "布局类型", "日期2", "抗体名称", "LD标识2", "测试名称2", 
    #     "查询内容", "测试内容", "LD标识3"
    # ]
    # result_dict = dict(zip(custom_keys, values))
    
    return result_dict

# 执行处理
param_str = data["params"]["params"]
result = extract_params_to_dict(param_str)

# 打印结果
print("处理后的字典：")
for k, v in result.items():
    print(f"{k}: {v}")