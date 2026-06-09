import cv2
import threading
import time

class CCTVStream:
    def __init__(self, source, reconnect_delay=2.0, max_retries=5):
        """
        source: เลข Index เว็บแคม, URL กล้อง RTSP หรือพาธไฟล์วิดีโอตัวอย่าง
        """
        self.source = source
        self.reconnect_delay = reconnect_delay
        self.max_retries = max_retries
        self.retry_count = 0
        self.failed_permanently = False
        
        self.cap = cv2.VideoCapture(source)
        
        # ตรวจสอบว่าแหล่งที่มาคือสตรีมสดจริง (RTSP / Webcam) หรือไม่
        self.is_live = False
        if isinstance(source, int):
            self.is_live = True
        elif isinstance(source, str):
            source_lower = source.lower()
            if (source_lower.startswith("rtsp://") or 
                source_lower.startswith("rtmp://") or 
                source_lower.startswith("http://") or 
                source_lower.startswith("https://")):
                self.is_live = True
                
        self.frame = None
        self.ret = False
        self.started = False
        self.read_lock = threading.Lock()
        
        if self.is_live:
            print(f"[CCTVStream] Detected LIVE stream ({source}). Starting worker thread...")
            self.start_thread()
        else:
            print(f"[CCTVStream] Detected OFFLINE file ({source}). Running in synchronous mode...")

    def start_thread(self):
        self.started = True
        self.thread = threading.Thread(target=self._update, args=())
        self.thread.daemon = True
        self.thread.start()

    def _update(self):
        while self.started:
            if not self.cap.isOpened():
                self.retry_count += 1
                print(f"[CCTVStream] Connection lost. Attempting reconnect {self.retry_count}/{self.max_retries} in {self.reconnect_delay}s...")
                
                if self.retry_count >= self.max_retries:
                    print("[CCTVStream] Max reconnection attempts reached. Stopping stream thread.")
                    self.failed_permanently = True
                    self.started = False
                    break
                    
                time.sleep(self.reconnect_delay)
                self.cap = cv2.VideoCapture(self.source)
                if self.cap.isOpened():
                    print("[CCTVStream] Reconnected successfully!")
                    self.retry_count = 0
                continue
                
            ret, frame = self.cap.read()
            if not ret:
                self.retry_count += 1
                print(f"[CCTVStream] Failed to read frame. Attempting reconnect {self.retry_count}/{self.max_retries} in {self.reconnect_delay}s...")
                self.cap.release()
                
                if self.retry_count >= self.max_retries:
                    print("[CCTVStream] Max reconnection attempts reached. Stopping stream thread.")
                    self.failed_permanently = True
                    self.started = False
                    break
                    
                time.sleep(self.reconnect_delay)
                self.cap = cv2.VideoCapture(self.source)
                if self.cap.isOpened():
                    print("[CCTVStream] Reconnected successfully!")
                    self.retry_count = 0
                continue
                
            with self.read_lock:
                self.ret = ret
                self.frame = frame
                self.retry_count = 0 # รีเซ็ตหากได้เฟรมปกติ
            time.sleep(0.01) # หน่วงเพื่อไม่ให้ใช้ CPU สูงเกินไป

    def read(self):
        if self.is_live:
            with self.read_lock:
                # คืนค่าสตรีมแบบคัดลอก (shallow copy) เพื่อความปลอดภัยในการทำงานต่าง Thread
                return self.ret, (self.frame.copy() if self.frame is not None else None)
        else:
            if self.cap.isOpened():
                return self.cap.read()
            return False, None

    def get_info(self):
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or fps > 100:
            fps = 25.0 # Fallback default FPS
        return width, height, fps

    def release(self):
        self.started = False
        if self.is_live and hasattr(self, 'thread'):
            self.thread.join(timeout=1.0)
        self.cap.release()
        print("[CCTVStream] Stream resources released.")
