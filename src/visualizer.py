import cv2
import numpy as np
import os

class CCTVVisualizer:
    def __init__(self, width, height, fps, panel_width=500, save_output=True, output_path="output_with_log.mp4"):
        self.width = width
        self.height = height
        self.fps = fps
        self.panel_width = panel_width
        self.save_output = save_output
        self.output_path = output_path
        
        self.out = None
        if self.save_output:
            # ตรวจสอบและสร้างโฟลเดอร์ปลายทางหากยังไม่มีอยู่
            dir_name = os.path.dirname(self.output_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.out = cv2.VideoWriter(self.output_path, fourcc, self.fps, (self.width + self.panel_width, self.height))
            print(f"[CCTVVisualizer] Initialized VideoWriter. Saving to: {self.output_path}")

    def draw_frame(self, annotated_frame, truck_states, overlaps_to_draw):
        """
        วาด overlay บนเฟรมวิดีโอ ขยายภาพ และวาด Log Panel ด้านซ้ายมือ
        """
        # 1. วาดเปอร์เซ็นต์ Overlap บนหัว รปภ.
        for gbox, overlap_pct in overlaps_to_draw:
            label = f"Overlap: {overlap_pct:.0%}"
            (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
            cv2.rectangle(annotated_frame, (int(gbox[0]), int(gbox[1]) - h - 20), 
                          (int(gbox[0]) + w, int(gbox[1]) - 5), (0, 0, 0), -1) # พื้นหลังทึบ
            cv2.putText(annotated_frame, label, (int(gbox[0]), int(gbox[1]) - 15), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2) # ข้อความสีเหลือง

        # 2. วาดแท็กความเร็วและสถานะของรถบรรทุกที่กำลังเคลื่อนไหว/จอด (เฉพาะคันที่ยังอยู่ในเฟรม)
        for tid, data in truck_states.items():
            if not data.get('is_active', False):
                continue
            tbox = data['box']
            status = data['status_text']
            speed = data['stable_speed']
            
            color = (255, 255, 255)
            if "PASSED" in status: color = (0, 255, 0)
            elif "ALERT" in status: color = (0, 0, 255)
            elif "STOPPED" in status: color = (0, 255, 255)
            elif "DETECTING" in status: color = (200, 200, 200)

            cv2.putText(annotated_frame, f"Tag {tid}: {status} | Spd: {speed:.2f}", 
                        (int(tbox[0]), int(tbox[3]) + 25), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # 3. สร้าง Canvas ขนาดขยายสำหรับภาพคู่ (วิดีโอขวา + แผงลอยซ้าย)
        canvas = np.zeros((self.height, self.width + self.panel_width, 3), dtype=np.uint8)
        canvas[:, self.panel_width:] = annotated_frame # วางเฟรมวิดีโอไว้ขวา

        # 4. วาดหัวข้อแผงควบคุมและเส้นแบ่งแถบด้านซ้าย
        cv2.putText(canvas, "CCTV TRUCK LOGS", (50, 50), cv2.FONT_HERSHEY_DUPLEX, 1.2, (255, 255, 255), 2)
        cv2.line(canvas, (20, 70), (self.panel_width - 20, 70), (255, 255, 255), 2)

        # 5. แสดงสถานะรถบรรทุกคันต่างๆ ด้านซ้ายมือ
        y_offset = 120
        for tid, data in truck_states.items():
            if y_offset > self.height - 50:
                break # ป้องกันตัวอักษรล้นลงขอบล่างจอ
                
            status = data['status_text']
            log_color = (255, 255, 255)
            if "PASSED" in status: log_color = (0, 255, 0)
            elif "ALERT" in status: log_color = (0, 0, 255)
            elif "STOPPED" in status: log_color = (0, 255, 255)
            
            log_entry = f"ID {tid}: {status}"
            cv2.putText(canvas, log_entry, (30, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, log_color, 2)
            y_offset += 40

        # 6. บันทึก Canvas ลงไฟล์วิดีโอ
        if self.out is not None:
            self.out.write(canvas)
            
        return canvas

    def release(self):
        if self.out is not None:
            self.out.release()
            print("[CCTVVisualizer] Finished writing video output.")
