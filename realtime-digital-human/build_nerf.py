"""
build_nerf.py - 包含许可证检查功能的 NeRF 构建模块
集成了 LicenseChecker 类用于时间锁和防篡改保护
"""
import os
import sys
import json
import hashlib
import base64
from datetime import datetime
from pathlib import Path
import asyncio

class AppState:
    def __init__(self):
        self.nerfreals: Dict[str, BaseReal] = {}
        self.pcs: set = set()
        self.instanceid_pc: Dict[str, RTCPeerConnection] = {}
        self.sessionid_ws: Dict[str, web.WebSocketResponse] = {}
        self.opt = None
        self.model = None
        self.avatar = None
        self.llm_response_queues: Dict[str, asyncio.Queue] = {}
        self.llm_ws_metrics: Dict[str, Dict[str, Any]] = {}
        self.cleaning_sessions: set[str] = set()
        self.offer_lock = asyncio.Lock()
        self.session_players: Dict[str, HumanPlayer] = {}

def show_error_dialog(message):
    """
    显示错误对话框
    """
    try:
        # 尝试使用 tkinter 显示对话框
        import tkinter as tk
        from tkinter import messagebox
        
        # 创建隐藏的根窗口
        root = tk.Tk()
        root.withdraw()
        # 确保对话框在最前面
        root.attributes('-topmost', True)
        
        messagebox.showerror("程序错误", message)
        
        # 销毁窗口
        root.destroy()
    except Exception as e:
        # 如果 tkinter 不可用，回退到命令行输出
        print(f"错误：{message}")

# ============================================
# 许可证检查器类（从 lic_check.py 合并）
# ============================================
class LicenseChecker:
    """许可证检查器 - 加密存储时间信息"""
    
    def __init__(self, license_file=None, secret_key="LicCheck_Secret_2024"):
        """
        初始化许可证检查器
        
        Args:
            license_file: 许可证文件路径（加密存储）
            secret_key: 加密密钥
        """
        self.secret_key = secret_key
        self.license_file = license_file or self._get_default_license_path()
        self.last_check_key = self._encrypt_key("last_check_time")
        self.start_time_key = self._encrypt_key("program_start_time")
        self.init_time_key = self._encrypt_key("first_init_time")
        
    def _get_default_license_path(self):
        """获取默认的许可证文件路径"""
        possible_paths = [
            Path(__file__).parent / ".lic_data.enc",
            Path.home() / ".lic_data.enc",
            Path(os.environ.get('APPDATA', '')) / ".lic_data.enc" if os.name == 'nt' else None,
        ]
        
        for path in possible_paths:
            if path:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    return str(path)
                except:
                    continue
        
        return ".lic_data.enc"
    
    def _encrypt_key(self, key_name):
        """生成加密的键名"""
        return hashlib.sha256(f"{self.secret_key}_{key_name}".encode()).hexdigest()[:16]
    
    def _xor_encrypt(self, data, key):
        """简单的 XOR 加密"""
        key_bytes = key.encode() if isinstance(key, str) else key
        data_bytes = data.encode() if isinstance(data, str) else data
        
        encrypted = bytes([data_bytes[i] ^ key_bytes[i % len(key_bytes)] for i in range(len(data_bytes))])
        return base64.b64encode(encrypted).decode()
    
    def _xor_decrypt(self, encrypted_data, key):
        """XOR 解密"""
        try:
            encrypted_bytes = base64.b64decode(encrypted_data.encode())
            key_bytes = key.encode() if isinstance(key, str) else key
            
            decrypted = bytes([encrypted_bytes[i] ^ key_bytes[i % len(key_bytes)] for i in range(len(encrypted_bytes))])
            return decrypted.decode()
        except:
            return None
    
    def _load_license_data(self):
        """加载并解密许可证数据"""
        if not os.path.exists(self.license_file):
            return {}
        
        try:
            with open(self.license_file, 'r', encoding='utf-8') as f:
                encrypted_data = json.load(f)
            
            decrypted_data = {}
            for enc_key, enc_value in encrypted_data.items():
                dec_value = self._xor_decrypt(enc_value, self.secret_key)
                if dec_value:
                    decrypted_data[enc_key] = dec_value
            
            return decrypted_data
        except Exception as e:
            print(f"警告：读取许可证文件失败：{e}")
            return {}
    
    def _save_license_data(self, data):
        """加密并保存许可证数据"""
        try:
            encrypted_data = {}
            for key, value in data.items():
                encrypted_data[key] = self._xor_encrypt(str(value), self.secret_key)
            
            os.makedirs(os.path.dirname(os.path.abspath(self.license_file)), exist_ok=True)
            
            with open(self.license_file, 'w', encoding='utf-8') as f:
                json.dump(encrypted_data, f, indent=2)
            
            return True
        except Exception as e:
            print(f"错误：保存许可证文件失败：{e}")
            return False
    
    def init_license(self, cutoff_datetime):
        """
        初始化许可证（首次运行时调用）
        
        Args:
            cutoff_datetime: 截止日期
        """
        data = self._load_license_data()
        
        # 只在首次运行时设置 first_init_time（不重复设置）
        if self.init_time_key not in data:
            data[self.init_time_key] = datetime.now().timestamp()
            print(f"首次初始化许可证，时间：{datetime.now()}")
        
        # 只在首次运行时设置 cutoff_datetime（不重复设置）
        cutoff_key = self._encrypt_key("cutoff_datetime")
        if cutoff_key not in data:
            data[cutoff_key] = cutoff_datetime.strftime('%Y-%m-%d %H:%M:%S')
            print(f"设置截止日期：{cutoff_datetime}")
        
        # 保存程序启动时间（每次运行都更新）
        data[self.start_time_key] = datetime.now().timestamp()
        
        # 不在这里更新 last_check_time，让 check_time_tampering 来更新
        
        return self._save_license_data(data)
    
    def check_time_tampering(self):
        """
        检测系统时间是否被篡改
        
        原理：
        - 保存每次检查的时间戳
        - 如果当前时间 < 上次检查时间 - 5分钟，说明时间被回退
        
        Returns:
            tuple: (是否篡改，错误信息)
        """
        data = self._load_license_data()
        current_time = datetime.now()
        
        # 获取上次检查时间
        last_check_str = data.get(self.last_check_key)
        
        if not last_check_str:
            # 首次运行，保存当前时间作为基准
            data[self.last_check_key] = current_time.timestamp()
            self._save_license_data(data)
            print(f"首次时间检查，记录基准时间：{current_time}")
            return False, None
        
        try:
            last_check = datetime.fromtimestamp(float(last_check_str))
            
            # 检测时间回退：如果当前时间比上次检查时间早超过 5 分钟
            time_diff_seconds = (last_check - current_time).total_seconds()
            
            if time_diff_seconds > 300:  # 5 分钟阈值
                error_msg = f"检测到系统时间被回退！\n上次检查时间：{last_check}\n当前系统时间：{current_time}\n时间差：{time_diff_seconds/60:.1f} 分钟"
                return True, error_msg
            
            # 检测时间跳跃过大（超过 24 小时），可能是时间被大幅前进
            if (current_time - last_check).total_seconds() > 86400:  # 24 小时
                print(f"警告：时间跳跃超过 24 小时，上次检查：{last_check}, 当前：{current_time}")
            
            # 更新上次检查时间
            data[self.last_check_key] = current_time.timestamp()
            self._save_license_data(data)
            
            return False, None
        except Exception as e:
            print(f"时间检查异常：{e}")
            return False, f"时间检查异常：{e}"
    
    def check_expiration(self):
        """
        检查是否过期
        
        Returns:
            tuple: (是否过期，截止日期，剩余时间)
        """
        data = self._load_license_data()
        
        if not data:
            return True, None, "许可证未初始化"
        
        cutoff_str = data.get(self._encrypt_key("cutoff_datetime"))
        if not cutoff_str:
            return True, None, "许可证数据损坏"
        
        try:
            cutoff = datetime.strptime(cutoff_str, '%Y-%m-%d %H:%M:%S')
            current = datetime.now()
            
            if current >= cutoff:
                return True, cutoff, "程序已过期"
            
            remaining = cutoff - current
            return False, cutoff, f"剩余 {remaining.days} 天 {remaining.seconds//3600} 小时"
        except Exception as e:
            return True, None, f"过期检查异常：{e}"

# ============================================
# 主业务函数
# ============================================
# 默认截止日期（如果没有被加密脚本注入，会使用此日期）
LICENSE_CUTOFF_DATE = "2027-6-13 18:30:00"

def build_nerfreal(session_id, opt, model, state: AppState):
    """
    创建并返回一个 LipReal 实例
    包含许可证检查功能：防时间篡改 + 过期验证
    """
    # ============================================
    # 许可证检查
    # ============================================
    # 创建许可证检查器
    checker = LicenseChecker()
    
    # 初始化许可证（设置截止日期）
    try:
        from datetime import datetime
        if 'LICENSE_CUTOFF_DATE' in globals():
            cutoff = datetime.strptime(LICENSE_CUTOFF_DATE, '%Y-%m-%d %H:%M:%S')
        else:
            # 默认截止日期
            cutoff = datetime.strptime("2027-12-31 23:59:59", '%Y-%m-%d %H:%M:%S')
        checker.init_license(cutoff)
    except Exception as e:
        print(f"警告：许可证初始化失败：{e}")
    
    # 检查时间篡改
    is_tampered, message = checker.check_time_tampering()
    if is_tampered:
        error_msg = f"许可证错误：{message}"
        show_error_dialog(error_msg)
        raise RuntimeError(error_msg)
    
    # 检查是否过期
    is_expired, cutoff_date, message = checker.check_expiration()
    if is_expired:
        error_msg = "程序已经过期"
        show_error_dialog(error_msg)
        raise RuntimeError(error_msg)
    
    print(f"✓ 许可证验证通过，{message}")
    
    # ============================================
    # 原始业务逻辑
    # ============================================
    opt.sessionid = session_id
    if opt.model == "wav2lip":
        from lipreal import LipReal

        nerfreal = LipReal(opt, state.model, state.avatar)
    return nerfreal
