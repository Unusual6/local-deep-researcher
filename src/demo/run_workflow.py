# run_workflow.py
import requests

print("🚀 Triggering workflow...")
resp = requests.post("http://127.0.0.1:8000/run")
print(resp.json())
