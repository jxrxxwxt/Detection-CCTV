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
            
        # กำหนด Camera ID และพาธไฟล์ CSV แยกกันสำหรับแต่ละกล้องเพื่อป้องกันไฟล์ชนกัน
        if config is not None and getattr(config, "active_camera_id", None):
            self.camera_id = config.active_camera_id
            self.log_file = os.path.join(self.log_dir, f"inspection_events_{self.camera_id}.csv")
        else:
            self.camera_id = "unknown_camera"
            self.log_file = os.path.join(self.log_dir, "inspection_events.csv")
        
        # เขียน Header ของตารางหากเพิ่งสร้างไฟล์ครั้งแรก
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Camera_ID", "Truck_ID", "Truck_Type", "Event_Status", "Image_Path"])
                
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
        และบันทึกรูปภาพหากเป็นเคส ALERT! (ส่ง LINE หากเปิดไว้)
        """
        if "PASSED" in status or "ALERT" in status:
            key = (truck_id, status)
            # ถ้าเหตุการณ์ ID นี้และสถานะนี้ยังไม่เคยบันทึก
            if key not in self.logged_events:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                image_path = "N/A"

                # หากเกิดเคส ALERT! ให้บันทึกรูปภาพลงเครื่องเสมอ (และส่ง LINE หากเปิดไว้)
                if "ALERT" in status:
                    msg = (
                        f"[ALERT] ตรวจพบการละเลยการตรวจเช็ก!\n"
                        f"กล้อง: {self.camera_id}\n"
                        f"ID รถ: {truck_id}\n"
                        f"ประเภทรถ: {truck_type}\n"
                        f"ผลลัพธ์: {status}\n"
                        f"วันเวลา: {timestamp}"
                    )
                    saved_path = self.notifier.send_alert(
                        message_text=msg,
                        frame=frame,
                        box=box,
                        truck_id=truck_id,
                        camera_id=self.camera_id
                    )
                    if saved_path:
                        image_path = saved_path
                    else:
                        image_path = "Failed to save image"

                # บันทึกข้อมูลแบบคอลัมน์ที่เพิ่มขึ้นลงไฟล์ CSV
                with open(self.log_file, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([timestamp, self.camera_id, truck_id, truck_type, status, image_path])
                    
                self.logged_events[key] = True
                print(f"[CCTVLogger] [EVENT REGISTERED] Camera: {self.camera_id} | ID {truck_id} ({truck_type}) -> {status} | Img: {image_path}")

