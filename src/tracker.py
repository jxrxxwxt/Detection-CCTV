import math

def calculate_overlap_percent(truck_box, guard_box):
    """
    คำนวณหาเปอร์เซ็นต์พื้นที่ของ Guard ที่เข้าไปซ้อนทับอยู่ในพื้นที่ของ Truck
    """
    x_left = max(truck_box[0], guard_box[0])
    y_top = max(truck_box[1], guard_box[1])
    x_right = min(truck_box[2], guard_box[2])
    y_bottom = min(truck_box[3], guard_box[3])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    guard_area = (guard_box[2] - guard_box[0]) * (guard_box[3] - guard_box[1])
    
    if guard_area == 0:
        return 0.0
        
    return intersection_area / guard_area

class TruckTracker:
    def __init__(self, buffer_size=30, stops_threshold=1.0, grace_period=15, overlap_threshold=0.30):
        self.buffer_size = buffer_size
        self.stops_threshold = stops_threshold
        self.grace_period = grace_period
        self.overlap_threshold = overlap_threshold
        self.truck_states = {}

    def update(self, trucks_info, guards_bboxes):
        """
        อัปเดตประวัติความเร็ว สถานะของรถบรรทุกแต่ละคัน และตรวจสอบเงื่อนไขการตรวจเช็ก
        คืนค่า: รายการของ tuple (guard_bbox, overlap_pct) เพื่อส่งไปให้ visualizer วาดผล
        """
        active_ids = set()
        overlaps_to_draw = []

        for tid, tbox, tcls in trucks_info:
            active_ids.add(tid)
            # ใช้จุดกึ่งกลางของฐานล้อ (Bottom-Center) ของรถ
            curr_x = (tbox[0] + tbox[2]) / 2
            curr_y = tbox[3]
            current_pos = (curr_x, curr_y)

            # ถ้าเจอ ID รถคันนี้ครั้งแรก
            if tid not in self.truck_states:
                is_unloaded = "unloaded" in tcls.lower()
                self.truck_states[tid] = {
                    'status_text': "INCOMING" if is_unloaded else "PASSED (Loaded)",
                    'type': "Unloaded" if is_unloaded else "Loaded",
                    'has_stopped': False,
                    'inspected': not is_unloaded,
                    'pos_history': [current_pos],
                    'frame_count': 0,
                    'stable_speed': 5.0,
                    'box': tbox,
                    'is_active': True
                }

            data = self.truck_states[tid]
            data['box'] = tbox
            data['is_active'] = True
            data['frame_count'] += 1
            data['pos_history'].append(current_pos)
            
            # เก็บเฉพาะขนาด Buffer ที่กำหนด
            if len(data['pos_history']) > self.buffer_size:
                data['pos_history'].pop(0)

            # คำนวณความเร็วเฉลี่ย (Moving Average) ย้อนหลัง
            history = data['pos_history']
            if len(history) >= 5:
                total_dist = math.hypot(history[-1][0] - history[0][0], history[-1][1] - history[0][1])
                data['stable_speed'] = total_dist / len(history)

            is_currently_stopped = (data['stable_speed'] < self.stops_threshold) and (data['frame_count'] > self.grace_period)

            if is_currently_stopped:
                data['has_stopped'] = True

            # ประมวลผลลอจิก State Machine สำหรับรถบรรทุกไม่มีของ (Unloaded)
            if data['type'] == "Unloaded" and not data['inspected']:
                # ล็อกสถานะหากเคยแจ้งเตือน ALERT! ไปแล้ว (State Lock)
                if "ALERT" in data['status_text']:
                    pass
                elif data['frame_count'] > self.grace_period:
                    if is_currently_stopped:
                        data['status_text'] = "STOPPED (Waiting Guard...)"
                        # คำนวณเปอร์เซ็นต์ทับซ้อนกับ รปภ. แต่ละคน
                        for gbox in guards_bboxes:
                            overlap_pct = calculate_overlap_percent(tbox, gbox)
                            overlaps_to_draw.append((gbox, overlap_pct))

                            # ถ้ารูปพิกัดทับซ้อนเกินค่าที่ตั้งไว้ (30%)
                            if overlap_pct >= self.overlap_threshold:
                                data['inspected'] = True
                                data['status_text'] = "PASSED (Inspected)"
                                break
                    # ถ้ารถเคยหยุดมาก่อนแล้วอยู่ดีๆ ขับเคลื่อนออกไปเร็วขึ้นโดยที่ยังไม่ได้ตรวจ (Inspected = False)
                    elif data['has_stopped'] and data['stable_speed'] > (self.stops_threshold + 0.3):
                        data['status_text'] = "ALERT! (Missed Inspection)"
                    elif not data['has_stopped']:
                        data['status_text'] = "MOVING (Incoming)"
                else:
                    data['status_text'] = "DETECTING..."

        # ทำเครื่องหมายรถที่ออกนอกกล้องไปแล้ว
        for tid, data in self.truck_states.items():
            if tid not in active_ids:
                data['is_active'] = False

        return overlaps_to_draw
