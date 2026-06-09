import cv2
from ultralytics import YOLO

class YOLODetector:
    def __init__(self, model_path, conf=0.25):
        self.model = YOLO(model_path)
        self.conf = conf
        # เลือกใช้อุปกรณ์ GPU (CUDA) หากมี เพื่อความเร็วสูงสุด
        self.device = 0 if cv2.cuda.getCudaEnabledDeviceCount() > 0 else 'cpu'
        print(f"[YOLODetector] Model loaded successfully on device: {self.device}")

    def track(self, frame, imgsz=640):
        """
        รันระบบติดตาม (Tracking) และวิเคราะห์วัตถุ
        """
        results = self.model.track(
            frame, 
            persist=True, 
            imgsz=imgsz, 
            conf=self.conf, 
            verbose=False, 
            device=self.device
        )
        return results

    def extract_objects(self, results):
        """
        แยกแยะพิกัดของ Guard และข้อมูลของ Truck ออกจากเฟรม
        คืนค่ากลับเป็น (guards_bboxes, trucks_info)
        """
        guards_bboxes = []
        trucks_info = []

        boxes = results[0].boxes
        if boxes is not None and boxes.id is not None:
            for box, track_id, cls_id in zip(boxes.xyxy.cpu().numpy(), boxes.id.cpu().numpy(), boxes.cls.cpu().numpy()):
                cls_name = self.model.names[int(cls_id)]
                # แยกว่าเป็น รปภ.
                if any(word in cls_name.lower() for word in ["guard", "security"]):
                    guards_bboxes.append(box)
                # แยกว่าเป็น รถบรรทุก (ทั้งแบบ Loaded และ Unloaded)
                elif any(word in cls_name.lower() for word in ["truck", "loaded", "unloaded"]):
                    trucks_info.append((int(track_id), box, cls_name))
                    
        return guards_bboxes, trucks_info
