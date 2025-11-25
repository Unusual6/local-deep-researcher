import base64
import socket
import struct
import codecs
import sys


# =============================================
# 工具函数：计算 CRC16（与 C# 的 Utility.CalculateCRC16 一致）
# =============================================
def calculate_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= (b << 8) & 0xFFFF
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF  # 强制 16bit
    return crc

# =============================================
# 1. 配置目标 UDP 服务器地址
# =============================================
UDP_IP = "127.0.0.1"  # 👈 改成运行 C# 程序的机器 IP
UDP_PORT = 1616       # 👈 改成 C# 程序监听的端口

# =============================================
# 2. 创建 UDP 客户端 Socket
# =============================================
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(5.0)  # 设置超时时间，避免卡死

# =============================================
# 3. 发送命令函数
# =============================================
def send_command(command: int, data: bytes = b''):
    # 包格式：包头(4) + 数据长度(2) + 命令(2) + 数据(N) + 校验(2)
    header = b'\x19\x81\x06\x17'
    length = len(data)
    packet_without_crc = header + struct.pack('<H', length) + struct.pack('<H', command) + data
    crc = calculate_crc16(packet_without_crc)
    packet = packet_without_crc + struct.pack('<H', crc)

    print(f"[发送] 命令: 0x{command:04X}, 数据: {data}")
    sock.sendto(packet, (UDP_IP, UDP_PORT))

    try:
        response, addr = sock.recvfrom(4096)
        print(f"[接收] 来自 {addr} 的响应: {response}")




        # 假设响应格式一致，尝试提取数据部分（跳过包头4 + 长度2 + 命令2，剩下的是数据，最后2字节是CRC）
        if len(response) >= 10:
            data_part = response[8:-2]  # 去掉包头4 + 长度2 + 命令2 + 数据N + 去掉最后2字节校验
            try:
                text = data_part.decode('gbk')  # 设备返回的文本通常是 GBK 编码
                print(f"[解析] 响应内容（GBK解码）: {text}")
                return text,response
            except UnicodeDecodeError:
                print(f"[解析] 响应是二进制或非文本，原始字节: {data_part}")
                return data_part
        else:
            print("[解析] 响应格式不符合预期，长度不足")
            return None
    except socket.timeout:
        print("[错误] 请求超时，未收到响应")
        return None

# =============================================
# 4. 主流程：获取列表 → 选择 → 启动
# =============================================
def main():
    # --- Step 1: 获取程序列表 (命令 0x0001) ---
    list_data = send_command(0x0001)
    list_data = "{脚本名称1}{脚本名称2}{脚本名称3}"
    if not list_data:
        print("❌ 获取程序列表失败")
        return

    # --- Step 2: 解析程序列表，比如 {配方1}{配方2} ---
    # 假设返回的是类似 "{配方1}{配方2}" 的字符串
    try:
        # 提取 {} 内的程序名
        import re
        recipes = re.findall(r'\{([^}]*)\}', list_data)
        if not recipes:
            print("❌ 未解析到任何程序名")
            return

        print("\n📋 可用程序列表：")
        for idx, name in enumerate(recipes):
            print(f"{idx + 1}. {name}")

        # --- Step 3: 用户选择 ---
        choice = input("\n请输入要启动的程序序号（如 1）: ")
        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(recipes):
                selected_recipe = recipes[choice_idx]
                print(f"✅ 您选择了程序: {selected_recipe}")
            else:
                print("❌ 序号无效")
                return
        except ValueError:
            print("❌ 请输入有效的数字")
            return

        # --- Step 4: 发送选定脚本命令  ---

        selected_bytes = selected_recipe.encode('gbk')

        send_command(0x0101, selected_bytes)

        # --- Step 5: 发送启动脚本命令 (0x0102) ---
        while True:
            do_choice = input('1.启动 '
                              '\n2.停止 '
                              '\n3.暂停 '
                              '\n4.恢复 '
                              '\n5.设置有效枪头位置 '
                              '\n6.更换枪头盒确认 '
                              '\n7.设置变量参数 '
                              '\n8.机械臂移动到原点 '
                              '\n9.正在运行中的通知信息-运行日志 '
                              '\n10.查看程序状态'
                              '\n请输入选择序号： ')
            if do_choice == '1':
                send_command(0x0102)
            elif do_choice == '2':
                send_command(0x0103)
                break
            elif do_choice == '3':
                send_command(0x0104, data=bytes([0]))
            elif do_choice == '4':
                send_command(0x0104, data=bytes([1]))
            elif do_choice == '5':
                # 设置有效枪头位置(不支持多枪头盒)
                # 假设你要设置枪头位置为 0（第0号枪头）
                tip_position = int(input("请输入枪头位置（0, 1, 2, ...）: "))  # 可以是 0, 1, 2, ... 根据实际情况设置
                # 将 int 转为 4 字节的小端 bytes，和 C# 的 BitConverter.GetBytes(ValidTipID) 一致
                data_bytes = tip_position.to_bytes(4, byteorder='little')
                # 发送命令 0x0105 + 参数（枪头位置）
                send_command(0x0105, data=data_bytes)
            elif do_choice == '6':
                send_command(0x0106)
            elif do_choice == '7':
                # 设置变量参数
                # 1. 定义变量名和变量值（可以是输入、配置或固定值）
                variable_name = str(input("请输入变量名（如温度、压力、时间）: "))  # 变量名，比如温度、压力、时间
                variable_value = str(input("请输入变量值（如36.5、ON、100）: "))  # 变量值，比如 36.5、ON、100
                # 2. 拼接为 "变量名\r\n变量值"，和 C# 一样
                variable_line = f"{variable_name}\r\n{variable_value}"
                # 3. 编码为字节（使用 gbk，与 C# 的 Encoding.Default 一致）
                variable_bytes = variable_line.encode('gbk')
                # 4. 转为 Base64 编码（和 C# 的 Convert.ToBase64String 一样）
                base64_str = base64.b64encode(variable_bytes).decode('ascii')  # 先得到 str
                # 5. 把 Base64 字符串再转回字节（GBK 编码），和 C# 一致：
                #    C# 是：Encoding.Default.GetBytes(base64code)
                final_data_bytes = base64_str.encode('gbk')  # 注意：这里是 gbk 编码 base64字符串
                # 6. 发送命令 0x0107 和最终的数据
                send_command(0x0107, data=final_data_bytes)
            elif do_choice == '8':
                send_command(0x0108)
            elif do_choice == '9':
                send_command(0x1000)
            elif do_choice == '10':
                data_part = send_command(0x0002)
                status_code = data_part[0]
                if status_code == 255:
                    print("无选中程序")
                elif status_code == 0:
                    print('空闲')
                elif status_code == 1:
                    print('运行中')
                elif status_code == 2:
                    print('暂停')
                elif status_code == 254:
                    print('未知错误')
    except Exception as e:
        print(f"[异常] 发生错误: {e}")

# =============================================
# 5. 启动程序
# =============================================
if __name__ == "__main__":

        main()
