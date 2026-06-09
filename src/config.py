import yaml
import os

class Config:
    def __init__(self, config_path="config/settings.yaml", camera_id=None):
        # ลองหาไฟล์ตั้งค่าที่สัมพันธ์กับสคริปต์ที่รัน
        if not os.path.exists(config_path):
            # Fallback ไปยังตำแหน่งโฟลเดอร์ของไฟล์นี้
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "config", "settings.yaml")
            
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found at {config_path}")
            
        with open(config_path, "r", encoding="utf-8") as f:
            self.data = yaml.safe_load(f)

        self.cameras = self.data.get("cameras", [])
        
        # ค้นหากล้องที่กำลังใช้งาน
        if camera_id is not None:
            self.active_camera_id = camera_id
        elif self.cameras:
            self.active_camera_id = self.cameras[0].get("id")
        else:
            self.active_camera_id = None

    def set_active_camera(self, camera_id):
        self.active_camera_id = camera_id

    def _get_active_camera_data(self):
        if self.active_camera_id and self.cameras:
            for cam in self.cameras:
                if cam.get("id") == self.active_camera_id:
                    return cam
        # กรณีไม่มีการตั้งค่าแบบกลุ่ม ให้ Fallback กลับไปใช้รูปแบบกล้องเดี่ยวแบบเดิม
        return self.data.get("camera", {})

    @property
    def camera_source(self):
        cam_data = self._get_active_camera_data()
        val = cam_data.get("source", 0)
        # ถ้าค่าเป็นตัวเลข เช่น 0 ให้แปลงเป็น int เพื่อให้ OpenCV ใช้เปิดเว็บแคมได้
        if isinstance(val, str) and val.isdigit():
            return int(val)
        return val

    @property
    def reconnect_delay(self):
        cam_data = self._get_active_camera_data()
        return cam_data.get("reconnect_delay", 2.0)

    @property
    def max_retries(self):
        cam_data = self._get_active_camera_data()
        return cam_data.get("max_retries", 5)

    @property
    def model_path(self):
        return self.data.get("yolo", {}).get("model_path", "models/loaded_unloaded_guard.pt")

    @property
    def imgsz(self):
        return self.data.get("yolo", {}).get("imgsz", 640)

    @property
    def conf(self):
        return self.data.get("yolo", {}).get("conf", 0.25)

    @property
    def ignore_regions(self):
        cam_data = self._get_active_camera_data()
        # เช็คว่ามี ignore_regions ในตัวกล้องหรือไม่
        if "ignore_regions" in cam_data:
            return cam_data.get("ignore_regions", [])
        # ถ้าไม่มี ให้ Fallback ไปใช้ของ YOLO ส่วนกลาง
        return self.data.get("yolo", {}).get("ignore_regions", [])

    @property
    def overlap_threshold(self):
        return self.data.get("logic", {}).get("overlap_threshold", 0.30)

    @property
    def stops_threshold(self):
        return self.data.get("logic", {}).get("stops_threshold", 1.0)

    @property
    def grace_period(self):
        return self.data.get("logic", {}).get("grace_period", 15)

    @property
    def buffer_size(self):
        return self.data.get("logic", {}).get("buffer_size", 30)

    @property
    def panel_width(self):
        return self.data.get("visualizer", {}).get("panel_width", 500)

    @property
    def show_window(self):
        import os
        if os.environ.get("DETECTOR_HEADLESS", "false").lower() == "true":
            return False
        return self.data.get("visualizer", {}).get("show_window", True)

    @property
    def save_output(self):
        return self.data.get("visualizer", {}).get("save_output", True)

    @property
    def output_path(self):
        path = self.data.get("visualizer", {}).get("output_path", "output_with_log.mp4")
        if self.active_camera_id:
            # แยกชื่อไฟล์และนามสกุล เช่น output_with_log.mp4 -> output_with_log_camera_1.mp4
            name, ext = os.path.splitext(path)
            return f"{name}_{self.active_camera_id}{ext}"
        return path

    @property
    def line_enable_alerts(self):
        return self.data.get("line_bot", {}).get("enable_alerts", False)

    @property
    def line_channel_access_token(self):
        return self.data.get("line_bot", {}).get("channel_access_token", "")

    @property
    def line_target_id(self):
        return self.data.get("line_bot", {}).get("target_id", "")

