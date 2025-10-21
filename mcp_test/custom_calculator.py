# custom_calculator.py
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# 定义输入参数格式
class CalculatorInput(BaseModel):
    num1: float
    num2: float

# 定义工具功能（计算两数之和）
@app.post("/calculate")
def calculate(input_data: CalculatorInput):
    return {"result": input_data.num1 + input_data.num2}