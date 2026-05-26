import os
import sqlite3
from logger import logger


class DeviceService:

    def __init__(self):
        self.db_path = 'device.db'
        db_exists = os.path.exists(self.db_path)
        if not db_exists:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE devices (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        deviceid TEXT NOT NULL,
                        webid TEXT
                    )
                ''')
                conn.commit()

    def register_device(self, deviceid, webid=None):
        """
        注册设备，如果 deviceid 已存在则更新 webid，否则插入新记录。
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM devices WHERE deviceid=?',
                           (deviceid, ))
            row = cursor.fetchone()
            if row:
                cursor.execute('UPDATE devices SET webid=? WHERE deviceid=?',
                               (webid, deviceid))
            else:
                cursor.execute(
                    'INSERT INTO devices (deviceid, webid) VALUES (?, ?)',
                    (deviceid, webid))
            conn.commit()

    def get_device_by_deviceid(self, deviceid):
        """
        根据 deviceid 查询设备信息。
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM devices WHERE deviceid=?',
                           (deviceid, ))
            return cursor.fetchone()

    def get_device_by_webid(self, webid):
        """
        根据 webid 查询设备信息。
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM devices WHERE webid=?', (webid, ))
            return cursor.fetchone()

    def list_devices(self):
        """
        返回所有设备信息。
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM devices')
            return cursor.fetchall()

    def close(self):
        pass  # 兼容旧接口，无需关闭
