# PC2的客户端代码（client.py）
import socket

# PC1的公网IP和映射的端口
server_public_ip = "123.45.67.89"  # 替换为PC1的公网IP
server_public_port = 8888  # 替换为路由器映射的外部端口

# 创建TCP套接字并连接
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((server_public_ip, server_public_port))
print("已连接到PC1服务器")

# 发送并接收数据
while True:
    message = input("请输入发送给PC1的消息（输入exit退出）：")
    client_socket.send(message.encode("utf-8"))
    if message == "exit":
        break
    # 接收回复
    reply = client_socket.recv(1024).decode("utf-8")
    print(f"收到PC1回复：{reply}")

# 关闭连接
client_socket.close()