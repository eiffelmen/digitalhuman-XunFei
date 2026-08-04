
def get_baseboard_serial_hash():
    serial_hash = os.environ.get("BASHBOARD_SERIAL_HASH", "")
    return serial_hash


def check_hardware():
    """硬件验证（预设的合法BASHBOARD序列号哈希值）"""
    valid_baseboard_serial_hash = os.environ.get("VALID_BASEBOARD_SERIAL_HASH", "")

    baseboard_serial = get_baseboard_serial_hash()
    if not baseboard_serial or not valid_baseboard_serial_hash:
        return False

    current_hash = baseboard_serial
    return current_hash == valid_baseboard_serial_hash


from datetime import datetime


def check_date():
    """时间验证（有效期至2025-08-31）"""
    expire_date = datetime(2025, 8, 31)
    return datetime.now() <= expire_date


# if not check_hardware():
#     print("错误：非授权服务器")
#     exit(1)
# if not check_date():
#     print("错误：程序已过期")
#     exit(1)
