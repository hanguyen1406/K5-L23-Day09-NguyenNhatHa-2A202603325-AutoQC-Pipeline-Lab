"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    lf = cfg["label_format"]
    tol = lf["overflow_tol"]
    min_px = lf["min_box_px"]
    max_frac = lf["max_box_frac"]
    dup_iou = lf["dup_box_iou"]

    issues = []
    n_classes = len(ds.classes)
    for img in ds.image_files():
        stem = img.stem
        lines = ds.read_label_lines(stem)
        if lines is None:
            continue
        size = ds.image_size(stem)
        seen: list[tuple[int, tuple[float, float, float, float]]] = []
        for line_no, text in lines:
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except ValueError as e:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem,
                                    f"dòng nhãn sai định dạng: {e}", line=line_no))
                continue
            if not 0 <= cls < n_classes:
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem,
                                    f"id lớp {cls} ngoài 0..{n_classes - 1}", line=line_no,
                                    extra={"class_id": cls}))
                continue
            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem,
                                    f"box rộng/cao không dương (w={w}, h={h})", line=line_no))
                continue

            left, right = cx - w / 2, cx + w / 2
            top, bottom = cy - h / 2, cy + h / 2
            overflow = max(0.0, -left, right - 1, -top, bottom - 1)
            if overflow > tol:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                                    f"box tràn khỏi ảnh {overflow:.4f}", line=line_no,
                                    extra={"overflow": overflow}))

            box = (cx, cy, w, h)
            if any(prev_cls == cls and iou_xywh(prev_box, box) > dup_iou for prev_cls, prev_box in seen):
                issues.append(Issue("label_format", ERROR, "DUP_BOX", stem,
                                    "box lặp với một dòng phía trước cùng lớp", line=line_no))

            if size is not None:
                short_px = min(w * size[0], h * size[1])
                if short_px < min_px:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem,
                                        f"cạnh ngắn {short_px:.1f}px < {min_px}px", line=line_no,
                                        extra={"short_side_px": round(short_px, 2)}))
            if w * h > max_frac:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem,
                                    f"box chiếm {w * h:.2%} diện tích ảnh", line=line_no,
                                    extra={"area_frac": round(w * h, 4)}))
            seen.append((cls, box))
    return issues
