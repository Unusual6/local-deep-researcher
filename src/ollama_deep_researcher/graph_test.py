import requests
import json

url = "http://120.204.73.73:8033/api/ai-gateway/v1/chat/completions"
headers = {
    "Authorization": "Bearer 1764728646727FBys1MQS2i7TX48XcRbrLxg",
    "Content-Type": "application/json",
}
payload = {
    "model": "GPT-oss-20b",
    "messages": [
        {"role": "user", "content": "hello"}
    ]
}

resp = requests.post(url, json=payload, headers=headers)
print("Status:", resp.status_code)
print("Raw response:")
print(resp.text)
