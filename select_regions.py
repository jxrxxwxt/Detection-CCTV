import cv2
import yaml
import os
import time
import argparse
from src.config import Config
from src.stream import CCTVStream

# ตัวแปรระดับ Global สำหรับจัดการการวาดด้วยเมาส์
drawing = False
ix, iy = -1, -1
cx, cy = -1, -1
current_regions = []

def mouse_callback(event, x, y, flags, param):
    global drawing, ix, iy, cx, cy, current_regions
    
    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        ix, iy = x, y
        cx, cy = x, y
        
    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing:
            cx, cy = x, y
            
    elif event == cv2.EVENT_LBUTTONUP:
        if drawing:
            drawing = False
            # บันทึกพิกัดสี่เหลี่ยม
            x1 = min(ix, x)
            y1 = min(iy, y)
            x2 = max(ix, x)
            y2 = max(iy, y)
            # บันทึกเมื่อกล่องมีพื้นที่กว้างและสูงเกิน 5 พิกเซล
            if (x2 - x1) > 5 and (y2 - y1) > 5:
                current_regions.append([x1, y1, x2, y2])

def main():
    global current_regions
    
    print("=" * 60)
    print(" CCTV Truck Inspection System: Interactive Ignore Region Selector ")
    print("=" * 60)
    
    # จัดการอาร์กิวเมนต์จาก Command Line
    parser = argparse.ArgumentParser(description="Interactive Ignore Region Selector")
    parser.add_argument("--camera", "-c", type=str, default=None, help="Camera ID to select regions for")
    args = parser.parse_args()
    
    # 1. โหลดข้อมูลการตั้งค่า
    try:
        config = Config(camera_id=args.camera)
    except FileNotFoundError as e:
        print(f"[Error] {e}")
        return

    # ตรวจสอบหากมีกล้องหลายตัวแต่ไม่ได้ระบุอาร์กิวเมนต์เข้ามา ให้แสดงเมนูเลือกกล้อง
    if args.camera is None and config.cameras:
        if len(config.cameras) > 1:
            print("\nกรุณาเลือกกล้องที่ต้องการตั้งค่า Ignore Regions:")
            for idx, cam in enumerate(config.cameras):
                print(f"  [{idx + 1}] ID: {cam.get('id')} - {cam.get('name', 'กล้อง ' + str(idx+1))}")
            
            while True:
                try:
                    choice = input(f"เลือกหมายเลข (1-{len(config.cameras)}): ").strip()
                    choice_idx = int(choice) - 1
                    if 0 <= choice_idx < len(config.cameras):
                        selected_cam_id = config.cameras[choice_idx].get("id")
                        config.set_active_camera(selected_cam_id)
                        print(f"-> เลือกกล้อง: {selected_cam_id}\n")
                        break
                    else:
                        print("หมายเลขไม่อยู่ในระบบ กรุณาระบุใหม่")
                except ValueError:
                    print("กรุณากรอกเฉพาะตัวเลข")

    print(f"Active Camera Setup: {config.active_camera_id}")

    # โหลดพิกัด Ignore Zones เดิมที่มีอยู่แล้วขึ้นมาแสดงผลต่อได้
    current_regions = list(config.ignore_regions)

    # 2. เริ่มดึงภาพจากกล้อง / วิดีโอ
    print(f"Connecting to source: {config.camera_source} ...")
    stream = CCTVStream(
        source=config.camera_source,
        reconnect_delay=config.reconnect_delay,
        max_retries=config.max_retries
    )
    
    # ดึงข้อมูลขนาดภาพ
    width, height, fps = stream.get_info()
    print(f"Source details: {width}x{height} @ {fps} FPS")

    # รออ่านเฟรมแรกให้พร้อม
    print("Reading first frame from camera stream...")
    ret, frame = stream.read()
    if stream.is_live:
        # หากเป็นกล้องสด อาจต้องสุ่มอ่านซ้ำเล็กน้อยเพื่อให้มีภาพใน Buffer
        for _ in range(30):
            ret, frame = stream.read()
            if ret and frame is not None:
                break
            time.sleep(0.1)

    if not ret or frame is None:
        print("[Error] Failed to read frame from stream. Cannot select regions.")
        stream.release()
        return

    # คำแนะนำผู้ใช้
    print("\n" + "*" * 60)
    print(f"คำแนะนำสำหรับการตีกรอบ Ignore Zone ของกล้อง '{config.active_camera_id}':")
    print("1. ลากเมาส์ (Click & Drag) เพื่อวาดกล่องสีส้มครอบพื้นที่ละเว้น")
    print("2. กล่องที่บันทึกแล้วจะแสดงเป็นสีแดงโปร่งแสงแบบถาวรบนหน้าจอ")
    print("3. ปุ่มคีย์บอร์ดลัด:")
    print("   [z] หรือ [Z] : ย้อนกลับ (Undo) ลบกล่องล่าสุดออก")
    print("   [c] หรือ [C] : ล้างทั้งหมด (Clear) ลบกล่องทั้งหมดที่เคยวาด")
    print("   [Spacebar] หรือ [s] : บันทึก (Save) พิกัดทั้งหมดและปิดโปรแกรม")
    print("   [Esc] หรือ [q] : ยกเลิก (Exit) ปิดโดยไม่เซฟ")
    print("*" * 60 + "\n")

    window_name = f"Select Ignore Regions for {config.active_camera_id}"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, width // 2 if width > 1280 else width, height // 2 if height > 720 else height)
    cv2.setMouseCallback(window_name, mouse_callback)

    while True:
        # โคลนภาพเฟรมดั้งเดิมเพื่อวาดทับ
        draw_frame = frame.copy()
        
        # 1. วาดกรอบ ignore_regions ทั้งหมดที่ยืนยันแล้ว
        for i, r in enumerate(current_regions):
            x1, y1, x2, y2 = r
            # ทำกรอบโปร่งแสงสีแดงอ่อน
            overlay = draw_frame.copy()
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), -1)
            cv2.addWeighted(overlay, 0.25, draw_frame, 0.75, 0, draw_frame)
            # วาดเส้นขอบสีแดง
            cv2.rectangle(draw_frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(draw_frame, f"Ignore #{i+1}", (x1 + 5, y1 + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
            
        # 2. วาดกรอบที่ผู้ใช้กำลังลากอยู่ ณ ปัจจุบัน (เส้นสีเหลือง)
        if drawing:
            x1 = min(ix, cx)
            y1 = min(iy, cy)
            x2 = max(ix, cx)
            y2 = max(iy, cy)
            cv2.rectangle(draw_frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
            cv2.putText(draw_frame, "Drawing...", (x1 + 5, y1 + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)

        cv2.imshow(window_name, draw_frame)
        
        key = cv2.waitKey(20) & 0xFF
        
        # ย้อนกลับ [z]
        if key == ord('z') or key == ord('Z'):
            if current_regions:
                current_regions.pop()
                print("-> ย้อนกลับ (Undo) ลบพื้นที่ที่เพิ่งเลือกออกแล้ว")
                
        # เคลียร์ [c]
        elif key == ord('c') or key == ord('C'):
            current_regions = []
            print("-> ล้างข้อมูลทั้งหมด (Clear All) เรียบร้อย")
            
        # บันทึกข้อมูล [Spacebar] หรือ [s]
        elif key == 32 or key == ord('s') or key == ord('S'):
            print("-> กำลังบันทึกพิกัดลงระบบ...")
            break
            
        # ออกโดยไม่เซฟ [Esc] หรือ [q]
        elif key == 27 or key == ord('q') or key == ord('Q'):
            print("-> ยกเลิกการตั้งค่า (ไม่มีการเซฟพิกัดใหม่)")
            stream.release()
            cv2.destroyAllWindows()
            return

    cv2.destroyAllWindows()

    # 3. บันทึกข้อมูลกลับลงไฟล์ config/settings.yaml
    config_path = "config/settings.yaml"
    if not os.path.exists(config_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_dir, "config", "settings.yaml")

    if os.path.exists(config_path):
        # อ่านไฟล์ดั้งเดิมก่อน เพื่อคงโครงสร้างและข้อมูลอื่นๆ ไว้
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # ค้นหาและอัปเดตพิกัดลงในรายการกล้องที่ระบุ
        cameras = data.get("cameras", [])
        updated = False
        if cameras:
            for cam in cameras:
                if cam.get("id") == config.active_camera_id:
                    cam["ignore_regions"] = current_regions
                    updated = True
                    break
        
        # กรณีไม่มีโครงสร้างกล้องเป็นลิสต์ (Fallback ไปยัง yolo.ignore_regions แบบโครงสร้างเดี่ยว)
        if not updated:
            if "yolo" not in data:
                data["yolo"] = {}
            data["yolo"]["ignore_regions"] = current_regions

        # เขียนทับกลับลงไฟล์
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
            
        print(f"\n[สำเร็จ] บันทึกข้อมูล Ignore Regions ({len(current_regions)} โซน) ของกล้อง '{config.active_camera_id}' เรียบร้อยแล้ว!")
    else:
        print(f"\n[ล้มเหลว] ไม่พบไฟล์ตั้งค่าที่ '{config_path}' ไม่สามารถบันทึกได้")

    stream.release()
    print("ปิดระบบกล้องเรียบร้อยครับ")

if __name__ == "__main__":
    main()
