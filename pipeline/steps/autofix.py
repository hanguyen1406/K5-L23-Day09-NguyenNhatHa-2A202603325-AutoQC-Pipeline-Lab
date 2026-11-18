"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401

DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
LINE_CODES = DROP_CODES | {"BOX_OUT_OF_IMAGE"}
REMOVE_CODES = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}


def _clip_box(box):
    """Cắt box (cx, cy, w, h) về [0,1]; None nếu sau khi cắt không còn diện tích."""
    cls, cx, cy, w, h = box
    x1, y1 = max(0.0, cx - w / 2), max(0.0, cy - h / 2)
    x2, y2 = min(1.0, cx + w / 2), min(1.0, cy + h / 2)
    if x2 <= x1 or y2 <= y1:
        return None
    return cls, (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1


def _fmt(box):
    cls, cx, cy, w, h = box
    return f"{cls} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def fix(ds, issues, cfg):
    fixes = []
    errors = [i for i in issues if i.severity == ERROR]

    # 1) Xoá ảnh hỏng / trùng / rò rỉ (kèm file nhãn của nó)
    removed = set()
    for i in errors:
        if i.code in REMOVE_CODES and i.image not in removed:
            img = ds.image_path(i.image)
            if img is None:
                continue
            img.unlink()
            ds.label_path(i.image).unlink(missing_ok=True)
            removed.add(i.image)
            fixes.append(dict(image=i.image, line="", action="remove_image",
                              before=img.name, after="(đã xoá ảnh + nhãn)"))

    # 2) Ghi lại tên lớp trong data.yaml (một lần là đủ)
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        before = ds.yaml_names()
        ds.yaml_path.write_text(
            yaml.safe_dump({"path": ".", "names": list(cfg["classes"])}, sort_keys=False, allow_unicode=True),
            encoding="utf-8")
        fixes.append(dict(image="data.yaml", line="", action="rename_classes",
                          before=str(before), after=str(list(cfg["classes"]))))

    # 3) Sửa từng file nhãn MỘT lần: gom lỗi theo số dòng gốc
    per_img = defaultdict(lambda: defaultdict(set))
    for i in errors:
        if i.code in LINE_CODES and i.line is not None and i.image not in removed:
            per_img[i.image][i.line].add(i.code)
    for stem in sorted(per_img):
        path = ds.label_path(stem)
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
        out = []
        for no, text in enumerate(raw, 1):
            codes = per_img[stem].get(no)
            if not codes:
                out.append(text)
                continue
            if codes & DROP_CODES:                      # xoá dòng thắng clip_box
                fixes.append(dict(image=stem, line=no, action="drop_line", before=text, after=""))
                continue
            clipped = _clip_box(parse_yolo_line(text))
            if clipped is None:                         # cắt xong rỗng -> xoá dòng
                fixes.append(dict(image=stem, line=no, action="drop_line", before=text, after=""))
                continue
            new = _fmt(clipped)
            out.append(new)
            fixes.append(dict(image=stem, line=no, action="clip_box", before=text, after=new))
        path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")

    # 4) Ảnh chưa có nhãn: không bịa file, chuyển người gán
    seen_missing = set()
    for i in errors:
        if (i.code == "MISSING_LABEL_FILE" and i.image not in removed
                and i.image not in seen_missing and ds.image_path(i.image) is not None):
            seen_missing.add(i.image)
            fixes.append(dict(image=i.image, line="", action="needs_label",
                              before="(không có file)", after="chuyển người gán"))

    return fixes
