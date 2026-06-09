import os
import cv2
import requests
import json
from datetime import datetime

class LINENotifier:
    def __init__(self, channel_access_token, target_id, enable_alerts=False):
        self.token = channel_access_token
        self.target_id = target_id
        self.enable_alerts = enable_alerts
        self.url = "https://api.line.me/v2/bot/message/push"
        
        # สร้างโฟลเดอร์สำหรับเก็บภาพแจ้งเตือนหากยังไม่มี
        self.alert_dir = "logs/alerts"
        if not os.path.exists(self.alert_dir):
            os.makedirs(self.alert_dir)

    def is_configured(self):
        """ตรวจสอบว่า Token ได้ถูกระบุอย่างถูกต้องหรือไม่"""
        if not self.token or self.token.startswith("YOUR_"):
            return False
        return True

    def upload_to_tmpfiles(self, file_path):
        """อัปโหลดรูปภาพไปยัง tmpfiles.org เพื่อรับ Direct Link (ลิงก์มีอายุ 60 นาที)"""
        url = "https://tmpfiles.org/api/v1/upload"
        try:
            print(f"[Notifier] Uploading {file_path} to TmpFiles...")
            with open(file_path, "rb") as f:
                files = {"file": f}
                response = requests.post(url, files=files, timeout=15)
            
            if response.status_code == 200:
                res_json = response.json()
                raw_url = res_json.get("data", {}).get("url")
                if raw_url:
                    direct_url = raw_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                    print(f"[Notifier] TmpFiles upload successful: {direct_url}")
                    return direct_url
            print(f"[Notifier] TmpFiles upload failed with status code {response.status_code}")
            return None
        except Exception as e:
            print(f"[Notifier] TmpFiles upload error: {e}")
            return None

    def upload_to_catbox(self, file_path):
        """อัปโหลดรูปภาพไปยัง Catbox.moe เพื่อรับ Direct Link HTTPS"""
        url = "https://catbox.moe/user/api.php"
        try:
            print(f"[Notifier] Uploading {file_path} to Catbox...")
            with open(file_path, "rb") as f:
                files = {"fileToUpload": f}
                data = {"reqtype": "fileupload"}
                response = requests.post(url, files=files, data=data, timeout=15)
            
            if response.status_code == 200:
                img_url = response.text.strip()
                print(f"[Notifier] Catbox upload successful: {img_url}")
                return img_url
            print(f"[Notifier] Catbox upload failed with status code {response.status_code}")
            return None
        except Exception as e:
            print(f"[Notifier] Catbox upload error: {e}")
            return None

    def upload_image(self, file_path):
        """อัปโหลดรูปภาพโดยพยายามใช้ TmpFiles เป็นหลัก และ Fallback ไปที่ Catbox"""
        # ลอง TmpFiles ก่อนเนื่องจากเสถียรและเร็วในปัจจุบัน
        url = self.upload_to_tmpfiles(file_path)
        if url:
            return url
            
        # ถ้า TmpFiles ล้มเหลว ให้ลอง Catbox
        print("[Notifier] TmpFiles failed, attempting fallback to Catbox...")
        url = self.upload_to_catbox(file_path)
        return url

    def send_alert(self, message_text, frame=None, box=None):
        """
        ส่งแจ้งเตือนไปที่ LINE บอท
        - message_text: ข้อความแจ้งเตือน
        - frame: เฟรมรูปภาพต้นฉบับ (numpy array)
        - box: พิกัดของรถบรรทุกในเฟรม [x1, y1, x2, y2]
        """
        if not self.enable_alerts:
            return

        img_url = None

        # 1. จัดการครอปและบันทึกรูปภาพหากมีการส่งเฟรมมา
        if frame is not None:
            try:
                h, w = frame.shape[:2]
                
                # วาดกรอบสีแดงพร้อมป้ายกำกับบนรูปภาพสำหรับ Context
                annotated_img = frame.copy()
                if box is not None:
                    x1, y1, x2, y2 = map(int, box)
                    # จำกัดขอบเขตพิกัดไม่ให้เกินขนาดรูปภาพ
                    x1, x2 = max(0, min(x1, w - 1)), max(0, min(x2, w - 1))
                    y1, y2 = max(0, min(y1, h - 1)), max(0, min(y2, h - 1))
                    
                    # วาดสี่เหลี่ยมสีแดงครอบรถบรรทุก
                    cv2.rectangle(annotated_img, (x1, y1), (x2, y2), (0, 0, 255), 3)
                    
                    # เขียนข้อความแจ้งเตือนกำกับบนภาพ
                    label = "ALERT: MISSED INSPECTION"
                    cv2.putText(annotated_img, label, (x1, max(y1 - 10, 25)), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)

                # บันทึกไฟล์ภาพลงเครื่องชั่วคราว
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_name = f"alert_{timestamp}.jpg"
                file_path = os.path.join(self.alert_dir, file_name)
                cv2.imwrite(file_path, annotated_img)
                print(f"[Notifier] Saved alert image locally to: {file_path}")

                # ถ้าไม่ได้กรอกการตั้งค่า LINE Token หรือใช้ค่า placeholder ให้ข้ามการอัปโหลดและส่ง LINE
                if not self.is_configured():
                    print("[Notifier] LINE Bot Token/Target ID is not configured or uses placeholder. Skipping upload and LINE message.")
                    return

                # 2. อัปโหลดรูปภาพขึ้น Cloud เพื่อเอา Direct URL (โดยพยายามใช้ TmpFiles และ fallback ไปที่ Catbox)
                img_url = self.upload_image(file_path)

            except Exception as e:
                print(f"[Notifier] Failed to process/save image: {e}")
                if not self.is_configured():
                    return
        else:
            if not self.is_configured():
                print("[Notifier] LINE Bot Token/Target ID is not configured or uses placeholder. Skipping alert.")
                return

        # 3. เตรียมการส่งข้อความไปยัง LINE Messaging API
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }

        messages = [
            {
                "type": "text",
                "text": message_text
            }
        ]

        # ถ้ามี URL ของรูปภาพ ให้แนบส่งไปด้วย
        if img_url:
            messages.append({
                "type": "image",
                "originalContentUrl": img_url,
                "previewImageUrl": img_url
            })

        # เช็คว่าเป็น Broadcast (ส่งหาผู้ติดตามทุกคน) หรือ Push (ส่งเจาะจงรายคน/กลุ่ม)
        is_broadcast = False
        if not self.target_id or self.target_id.lower() in ["broadcast", "forecast", "all", "your_line_user_or_group_id"]:
            is_broadcast = True
            request_url = "https://api.line.me/v2/bot/message/broadcast"
            payload = {
                "messages": messages
            }
        else:
            request_url = self.url
            payload = {
                "to": self.target_id,
                "messages": messages
            }

        # 4. ส่ง HTTP Request ไปยัง LINE API
        try:
            if is_broadcast:
                print("[Notifier] Sending BROADCAST message to all followers...")
            else:
                print(f"[Notifier] Sending PUSH message to LINE target: {self.target_id}...")
                
            response = requests.post(request_url, headers=headers, data=json.dumps(payload), timeout=10)
            if response.status_code == 200:
                print("[Notifier] LINE notification sent successfully!")
            else:
                print(f"[Notifier] LINE notification failed: Status {response.status_code}, Response: {response.text}")
        except Exception as e:
            print(f"[Notifier] Error sending LINE request: {e}")
