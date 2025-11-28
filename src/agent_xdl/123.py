import json,re
s = '\n\n{\n"hardware": ["high-temperature-furnace", "stirrer", "crucible"],\n"reagents": ["aluminum-ingot", "silicon-alloy", "magnesium-alloy", "flux", "mold-release-agent"],\n"steps": [\n    {\n      "action": "Add",\n      "reagent": "aluminum-ingot",\n      "vessel": "crucible",\n      "volume": "500 g"\n    },\n    {\n      "action": "Heat",\n      "vessel": "crucible",\n      "temperature": "750°C",\n      "duration": "1h"\n    },\n    {\n      "action": "Add",\n      "reagent": "silicon-alloy",\n      "vessel": "crucible",\n      "volume": "30 g"\n    },\n    {\n      "action": "Add",\n      "reagent": "magnesium-alloy",\n      "vessel": "crucible",\n      "volume": "10 g"\n    },\n    {\n      "action": "Stir",\n      "vessel": "crucible",\n      "speed": "300"\n    },\n    {\n      "action": "Pour",\n      "vessel": "mold",\n      "volume": "450 g"\n    }\n  ]\n}'
# llm_data = json.loads(s)
# print("解析成功：", llm_data)
json_pattern = re.compile(r'```(?:json)?\s*\n([\s\S]*?)\n```', re.IGNORECASE)
s = s.encode('utf-8').decode('utf-8')  
match = json_pattern.search(s)
if match:
    pure_json = match.group(1).strip()
else:
    pure_json = s.strip()

# 步骤3：容错解析
try:
    # 额外修复℃编码问题（可选）
    pure_json = pure_json.replace('\xc2\xb0C', '°C')
    llm_data = json.loads(pure_json)
    print("解析成功：", llm_data)
except json.JSONDecodeError as e:
    print("解析失败：", llm_data)
# print(s.items())

# x = ''
# for i in s.items():
#     if i[0] == 'action':
#         x += i[1]
#         continue
#     x += f' {i[0]}="{i[1]}"' 
# print(x)