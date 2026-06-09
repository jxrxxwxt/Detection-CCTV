import cv2
import time
from src.config import Config
from src.stream import CCTVStream
from src.detector import YOLODetector
from src.tracker import TruckTracker
from src.visualizer import CCTVVisualizer
from src.logger import CCTVLogger

import argparse

def main():
    # จัดการอาร์กิวเมนต์จาก Command Line
    parser = argparse.ArgumentParser(description="CCTV Truck Inspection System")
    parser.add_argument("--camera", "-c", type=str, default=None, help="Camera ID to run detection on")
    args = parser.parse_args()

    # 1. โหลดข้อมูลการตั้งค่าจากไฟล์ภายนอก
    try:
        config = Config(camera_id=args.camera)
    except FileNotFoundError as e:
        print(f"[Error] {e}")
        return

    # หากไม่ได้ระบุกล้องตัวใดตัวหนึ่งเข้ามา และมีกล้องลงทะเบียนไว้มากกว่า 1 ตัว
    # ให้ทำการรันกล้องทั้งหมดคู่ขนานกันแยกเป็นแต่ละ Process
    if args.camera is None and len(config.cameras) > 1:
        import subprocess
        import sys
        
        print(f"\n[Main] Detected {len(config.cameras)} cameras. Starting concurrent processes...")
        processes = []
        for cam in config.cameras:
            cam_id = cam.get("id")
            cam_name = cam.get("name", cam_id)
            print(f"[Main] Spawning subprocess for {cam_name} (ID: {cam_id})...")
            p = subprocess.Popen([sys.executable, "main.py", "--camera", cam_id])
            processes.append(p)
            
        try:
            # รอให้ทุก Process ทำงานเสร็จสิ้น หรือจนกว่าจะมีการปิดโปรแกรม
            for p in processes:
                p.wait()
        except KeyboardInterrupt:
            print("\n[Main] KeyboardInterrupt received. Terminating all camera processes...")
            for p in processes:
                p.terminate()
            print("[Main] All processes terminated successfully.")
        return

    # 2. เชื่อมโยงช่องทางสตรีมภาพ (ไฟล์วิดีโอ หรือ RTSP กล้องวงจรปิด)
    stream = CCTVStream(
        source=config.camera_source,
        reconnect_delay=config.reconnect_delay,
        max_retries=config.max_retries
    )
    
    width, height, fps = stream.get_info()
    print(f"[Main] Video Dimensions: {width}x{height} @ {fps} FPS")

    # 3. โหลดและสร้าง YOLO Detector
    detector = YOLODetector(
        model_path=config.model_path,
        conf=config.conf
    )

    # 4. สร้างตัวติดตามสำหรับจดจำสถานะและพิกัดล้อรถ
    tracker = TruckTracker(
        buffer_size=config.buffer_size,
        stops_threshold=config.stops_threshold,
        grace_period=config.grace_period,
        overlap_threshold=config.overlap_threshold
    )

    # 5. สร้างตัววาด GUI และจัดการขยายขนาด Canvas
    visualizer = CCTVVisualizer(
        width=width,
        height=height,
        fps=fps,
        panel_width=config.panel_width,
        save_output=config.save_output,
        output_path=config.output_path
    )

    # 6. สร้างตัวบันทึกเหตุการณ์ลงไฟล์ CSV และส่งแจ้งเตือน LINE
    logger = CCTVLogger(config=config)

    # ตั้งค่าหน้าต่างแสดงผลสด
    window_name = f"CCTV Truck Inspection System - {config.active_camera_id}" if config.active_camera_id else "CCTV Truck Inspection System"
    if config.show_window:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, width + config.panel_width, height)

    print("[Main] System initialized successfully. Processing frames...")

    try:
        while True:
            ret, frame = stream.read()
            if not ret or frame is None:
                # ถ้ากล้องตัดการเชื่อมต่อแบบถาวร (Reconnect ครบโควต้า) ให้ปิดระบบ
                if stream.failed_permanently:
                    print("[Main] Camera connection lost permanently. Shutting down system...")
                    break
                
                # ถ้าระบบไม่ได้อ่านภาพสด (อ่านจากไฟล์วิดีโอ) และอ่านจนสุดไฟล์แล้ว ให้ปิดโปรแกรม
                if not stream.is_live:
                    print("[Main] Video file processing complete.")
                    break
                else:
                    # ถ้าเป็นกล้องสด RTSP สัญญาณหลุด จะรอรับสัญญาณใหม่ (แต่ไม่เกินจำนวนครั้งสูงสุด)
                    time.sleep(0.1)
                    continue

            # เก็บสำเนาภาพดั้งเดิมไว้สำหรับแสดงผล/คืนค่าพิกัดให้มนุษย์เห็น
            original_frame = frame.copy()
            h_f, w_f = frame.shape[:2]

            # ถมดำบริเวณ Ignore บน frame ที่จะใช้ป้อนให้ YOLO
            for region in config.ignore_regions:
                if len(region) == 4:
                    x1, y1, x2, y2 = map(int, region)
                    # จำกัดพิกัดให้อยู่ในขอบเขตภาพเพื่อป้องกัน Error
                    x1, x2 = min(x1, x2), max(x1, x2)
                    y1, y2 = min(y1, y2), max(y1, y2)
                    x1 = max(0, min(x1, w_f - 1))
                    y1 = max(0, min(y1, h_f - 1))
                    x2 = max(0, min(x2, w_f - 1))
                    y2 = max(0, min(y2, h_f - 1))
                    
                    if (x2 - x1) > 0 and (y2 - y1) > 0:
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 0), -1)

            # ทำการติดตามความเคลื่อนไหว (YOLO track บนภาพที่ถูกถมดำแล้ว)
            results = detector.track(frame, imgsz=config.imgsz)
            
            # แยกแยะข้อมูลประเภทพิกัดของ รปภ. และของรถบรรทุก
            guards_bboxes, trucks_info = detector.extract_objects(results)
            
            # คำนวณความเร็วเฉลี่ย, จุดฐานล้อ, และหาพิกัดทับซ้อนของ รปภ.
            overlaps_to_draw = tracker.update(trucks_info, guards_bboxes)

            # ค้นหาและบันทึกรูปภาพที่ชัดที่สุด (Bounding Box ใหญ่ที่สุด) ของรถบรรทุกแต่ละคัน
            for tid, tbox, tcls in trucks_info:
                if tid in tracker.truck_states:
                    data = tracker.truck_states[tid]
                    area = (tbox[2] - tbox[0]) * (tbox[3] - tbox[1])
                    if 'max_area' not in data or area > data['max_area']:
                        data['max_area'] = area
                        data['best_frame'] = original_frame.copy()
                        data['best_box'] = tbox
            
            # ดึงกรอบภาพและป้ายกำกับเริ่มต้นที่ YOLO วาดไว้ (ซึ่งยังมีกล่องดำทึบอยู่)
            annotated_frame = results[0].plot()

            # คืนค่าภาพส่วนที่ถูกถมดำจาก original_frame กลับมาใน annotated_frame
            for region in config.ignore_regions:
                if len(region) == 4:
                    x1, y1, x2, y2 = map(int, region)
                    x1, x2 = min(x1, x2), max(x1, x2)
                    y1, y2 = min(y1, y2), max(y1, y2)
                    x1 = max(0, min(x1, w_f - 1))
                    y1 = max(0, min(y1, h_f - 1))
                    x2 = max(0, min(x2, w_f - 1))
                    y2 = max(0, min(y2, h_f - 1))
                    
                    if (x2 - x1) > 0 and (y2 - y1) > 0:
                        # คืนค่าพิกเซลเดิมกลับมา
                        annotated_frame[y1:y2, x1:x2] = original_frame[y1:y2, x1:x2]
                        
                        # ทำการถมดำจางๆ (Semi-transparent overlay) 30% ความทึบแสง
                        overlay = annotated_frame.copy()
                        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 0), -1)
                        cv2.addWeighted(overlay, 0.3, annotated_frame, 0.7, 0, annotated_frame)
                        
                        # วาดขอบเส้นสีแดงบางๆ และป้ายกำกับ
                        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        cv2.putText(annotated_frame, "AI IGNORED ZONE", (x1 + 10, y1 + 25),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            # บันทึกสถานะสำคัญลงประวัติ CSV (หากเป็น PASSED หรือ ALERT!)
            for tid, data in tracker.truck_states.items():
                logger.log_event(
                    truck_id=tid,
                    truck_type=data['type'],
                    status=data['status_text'],
                    frame=data.get('best_frame'),
                    box=data.get('best_box')
                )

            # สร้างวิดีโอ Canvas คู่ที่มี Log Panel อยู่ฝั่งซ้ายมือ
            canvas = visualizer.draw_frame(
                annotated_frame=annotated_frame,
                truck_states=tracker.truck_states,
                overlaps_to_draw=overlaps_to_draw
            )

            # แสดงผลภาพสดบนหน้าต่าง OpenCV
            if config.show_window:
                cv2.imshow(window_name, canvas)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("[Main] Process stopped by user keyboard input ('q').")
                    break

    except KeyboardInterrupt:
        print("[Main] Process interrupted by keyboard (Ctrl+C).")
        
    finally:
        # คืนทรัพยากรทุกส่วนให้กับระบบ
        stream.release()
        visualizer.release()
        if config.show_window:
            cv2.destroyAllWindows()
            
    print("[Main] System termination clean.")

if __name__ == "__main__":
    main()
