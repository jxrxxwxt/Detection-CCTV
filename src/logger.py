import os
import csv
from datetime import datetime

from src.notifier import LINENotifier

class CCTVLogger:
    def __init__(self, log_dir="logs", config=None):
        self.log_dir = log_dir
        # สร้างโฟลเดอร์สำหรับเก็บ Log หากยังไม่มี
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        # กำหนดพาธไฟล์ CSV
        self.log_file = os.path.join(self.log_dir, "inspection_events.csv")
        
        # เขียน Header ของตารางหากเพิ่งสร้างไฟล์ครั้งแรก
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Truck_ID", "Truck_Type", "Event_Status"])
                
        # พจนานุกรมประวัติเพื่อไม่ให้เขียนประวัติซ้ำซากในทุกๆ เฟรมที่สถานะตรงกัน
        self.logged_events = {}

        # ตั้งค่าระบบส่งการแจ้งเตือน LINE
        if config is not None:
            self.notifier = LINENotifier(
                channel_access_token=config.line_channel_access_token,
                target_id=config.line_target_id,
                enable_alerts=config.line_enable_alerts
            )
        else:
            self.notifier = LINENotifier("", "", enable_alerts=False)

    def log_event(self, truck_id, truck_type, status, frame=None, box=None):
        """
        บันทึกเหตุการณ์สถานะสิ้นสุดลงในระบบ (เฉพาะ PASSED หรือ ALERT! เท่านั้น)
        และแจ้งเตือนไปยัง LINE บอท หากมีการตั้งค่าไว้
        """
        if "PASSED" in status or "ALERT" in status:
            key = (truck_id, status)
            # ถ้าเหตุการณ์ ID นี้และสถานะนี้ยังไม่เคยบันทึก
            if key not in self.logged_events:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(self.log_file, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([timestamp, truck_id, truck_type, status])
                self.logged_events[key] = True
                print(f"[CCTVLogger] [EVENT REGISTERED] ID {truck_id} ({truck_type}) -> {status}")

                # หากเกิดเคส ALERT! และบอท LINE เปิดใช้งานแจ้งเตือนอยู่
                if "ALERT" in status and self.notifier.enable_alerts:
                    msg = (
                        f"[ALERT] ตรวจพบการละเลยการตรวจเช็ก!\n"
                        f"ID รถ: {truck_id}\n"
                        f"ประเภทรถ: {truck_type}\n"
                        f"ผลลัพธ์: {status}\n"
                        f"วันเวลา: {timestamp}"
                    )
                    self.notifier.send_alert(msg, frame=frame, box=box)

