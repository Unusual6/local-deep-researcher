# PC1的服务器代码（server.py）
import socket

# 创建TCP套接字
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# 绑定本地IP和端口（端口可自定义，如8888，需确保未被占用）
local_ip = "0.0.0.0"  # 监听所有局域网IP
local_port = 8888
server_socket.bind((local_ip, local_port))
# 开始监听（最大连接数5）
server_socket.listen(5)
print(f"PC1服务器启动，监听 {local_ip}:{local_port}...")

# 等待PC2连接
client_socket, client_addr = server_socket.accept()
print(f"PC2已连接：{client_addr}")

# 接收并发送数据
while True:
    data = client_socket.recv(1024).decode("utf-8")  # 接收数据（最大1024字节）
    if not data or data == "exit":
        break
    print(f"收到PC2消息：{data}")
    # 回复消息
    reply = input("请输入回复PC2的消息：")
    client_socket.send(reply.encode("utf-8"))

# 关闭连接
client_socket.close()
server_socket.close()