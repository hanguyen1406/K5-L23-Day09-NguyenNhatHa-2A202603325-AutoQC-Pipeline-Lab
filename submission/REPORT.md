# Báo cáo Day 09 — Nguyễn Nhật Hạ, 2A202603325

## 1. Kết luận trước

**Release.** 224 ảnh vào, **202 ảnh ra dataset** (718 box; loại 22 ảnh ngay ở bước nhận dữ liệu). Sau 35 thay đổi tự động và 80 ảnh người duyệt, còn **0 lỗi bắt buộc** và **16/202 ảnh cảnh báo (7,9%)**, dưới ngưỡng Hold 10% → Release. Lý do chính: lỗi hình thức (định dạng, class id/tên, box tràn/trùng) đã được máy sửa; 6 ảnh thiếu nhãn được người xử lý; cảnh báo còn lại là **nghi ngờ ngữ nghĩa** của model, không phải lỗi chắc chắn.

## 2. Lỗi và phân việc

Nguồn: `02_error_list_v1.csv` — 36 error + 112 warn trên 202 ảnh đã nhận (22 ảnh bị loại ở intake vẫn có dòng lỗi).

| Mã lỗi | Số ảnh / dòng | Ai sửa | Vì sao |
|---|---:|---|---|
| DUP_IMAGE_EXACT | 8 / 8 | máy | trùng byte (md5), không thêm thông tin |
| DUP_IMAGE_NEAR | 4 / 4 | máy | pHash ≤ 10, gần trùng |
| LEAK_TEST | 5 / 5 | máy | trùng ảnh trong `test`/`gold_val` — không được train |
| CORRUPT_IMAGE | 2 / 2 | máy | không decode được |
| BAD_SIZE | 3 / 3 | máy | cạnh ngắn < 250 px |
| BAD_CLASS_ID | 6 / 6 | máy | id ngoài 0–3 → xoá dòng |
| BAD_CLASS_NAME | 1 / 2 | máy | `Person`, `Bus` sai tên → rename trong `data.yaml` |
| BAD_FORMAT | 3 / 3 | máy | thiếu cột / NaN / không parse → xoá dòng |
| BOX_ZERO | 4 / 4 | máy | w hoặc h = 0 → xoá dòng |
| BOX_OUT_OF_IMAGE | 8 / 8 | máy | tràn > 0.002 → clip về biên |
| DUP_BOX | 7 / 7 | máy | IoU > 0.9 cùng lớp → xoá dòng |
| MISSING_LABEL_FILE | 6 / 6 | người | máy không tự tạo nhãn; đưa vào hàng đợi ưu tiên 10 |
| EMPTY_LABEL | 12 / 12 | người | "nền hay thiếu nhãn?" — máy không tự quyết |
| BOX_TINY | 4 / 6 | người | cạnh ngắn 8,9–11,9 px (< 12 px) |
| BOX_HUGE | 3 / 3 | người | box chiếm 97–98,8% diện tích |
| CLASS_RARE | `<dataset>` / 4 | máy | id lạ còn sót trước autofix; dòng chứa chúng bị xoá |
| POSSIBLE_MISSING | 32 / 32 | người | model thấy vật nhưng nhãn không có box |
| POSSIBLE_FALSE_POS | 27 / 29 | người | nhãn có box nhưng model không khớp |
| POSSIBLE_WRONG_CLASS | 14 / 14 | người | IoU cao nhưng khác lớp |
| POSSIBLE_LOOSE_BOX | 12 / 12 | người | cùng lớp nhưng IoU < 0,5 |

`05_review_queue.csv` có **102 ảnh**, xếp theo tổng trọng số: 6 ảnh `NEEDS_LABEL` được 10 điểm nên đứng đầu (riêng `img_0020` 11,524 vì vừa có dòng bị xoá vừa có nghi ngờ missing/wrong-class), sau đó là wrong-class (3), missing/false-pos (2), loose-box (1,5), cảnh báo nhẹ (0,3–1). Với ngân sách **80 ảnh**, người xem được **78 lỗi ngữ nghĩa** ở v2: toàn bộ 32 MISSING, 12 LOOSE, 14 WRONG_CLASS và 20/29 FALSE_POS. 22 ảnh cuối không ai xem, còn lại 9 FALSE_POS.

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---:|---:|---|---|
| `duplicates.phash_dist` | 2 | **10** | DUP_IMAGE_NEAR: 1,00 / 0,50 → **1,00 / 0,67** | d=16 cho recall 0,83 nhưng khi mở ảnh thật, các cặp mới là **hai cảnh khác nhau** → sẽ xoá oan. d=10 bắt được cặp trùng thật xa nhất (cảnh ghế băng `0061`/`0186`) mà vẫn giữ precision 1,00. |
| `second_opinion.conf` | 0,25 | **0,80** | WRONG_CLASS 0,56/0,83 → **1,00/0,83**; MISSING 0,50/1,00 → **0,67/0,75**; LOOSE 0,29/0,40 → **0,50/0,20**; FALSE_POS 0,31/1,00 → 0,31/1,00 | 0,80 loại hết false positive của WRONG_CLASS và giữ recall 0,83; hàng đợi raw còn 102 ảnh (vẫn > ngân sách 80). Đánh đổi: LOOSE rơi 0,40 → 0,20, MISSING 1,00 → 0,75. Không chọn > 0,85 vì hàng đợi rỗng giả. |

**Một chỗ calibration có thể đánh lừa:** sweep nói `phash_dist=16` tốt nhất (NEAR 1,00/0,83, 0 FP), nhưng calib chỉ có 6 cặp near + 3 cặp exact do người ta **cố tình tạo**, không đại diện cho raw. Khi đối chiếu raw ở d=16, cặp mới nhất là ảnh trượt tuyết với ảnh tennis, và ảnh bàn laptop với ảnh test bóng chày — hoàn toàn khác nhau. Tương tự, precision của FALSE_POS **không đổi** qua mọi mức conf (0,31) vì mã này dùng `fp_conf=0,1` chứ không dùng khoá đang sweep; nhìn bảng dễ tưởng "tăng conf không cải thiện FP", thực ra là do thiết kế.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

**(a) Gate chặn đúng.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`:

- nhận 202/224, v1 có 36 lỗi/112 cảnh báo, 35 fix, v2 còn **6 lỗi** (đều `MISSING_LABEL_FILE`), hàng đợi 102 ảnh;
- người duyệt **0 ảnh** → v3 vẫn 6 lỗi → **REWORK**, mã thoát **20**;
- log ghi `Bước 5/5 KHÔNG xuất: còn lỗi bắt buộc (Rework)` và thư mục `work/exp_nb` **không được tạo**.

**(b) Ít nhất 2 điểm mù có bằng chứng:**

1. **Conf 0,80 bỏ sót box lỏng và một số missing.** Calib: LOOSE chỉ bắt 1/5 (recall 0,20), MISSING bắt 6/8. Trong v3 còn đúng 1 LOOSE với IoU **0,49** (sát ngưỡng 0,5) và 1 MISSING với conf **0,81** — chỉ hơi vượt ngưỡng nên lọt.
2. **Ảnh đã duyệt được coi là sạch.** 11 ảnh đã duyệt vẫn còn **13 cảnh báo máy** ở v3 (9 FALSE_POS, 1 WRONG_CLASS, 1 LOOSE, 1 MISSING, 1 TINY) nhưng gate ẩn toàn bộ vì nằm trong tập `reviewed`. Nếu người duyệt sai, lỗi vẫn vào Release mà không bị đếm.
3. **pHash chỉ bắt biến đổi nhẹ.** Calib NEAR sót 2/6; ảnh bị crop/đổi phối cảnh mạnh sẽ vượt d=10 (và `LEAK_TEST` cũng chỉ so pHash với test/gold_val). Ngoài ra 6 nhãn rỗng được phát hành: pipeline không phân biệt được "ảnh nền" với "thiếu nhãn" — chỉ cảnh báo.
4. **False positive của model khá nhiễu.** Precision FALSE_POS trên calib chỉ **0,31** (5 TP/16 cảnh báo), không đổi khi tăng conf; ngân sách 80 bị chiếm chỗ bởi các báo động giả.

## 5. Train: raw vs clean

**Chưa chạy train** (chưa có GPU/Colab trong thời gian làm bài), nên không có bảng `comparison.md` và **không kết luận** clean tốt hơn raw. Kế hoạch khi có T4: mở `notebooks/day09_train_compare.ipynb`, train yolo26n 20 epoch, 2 seed, cùng val/test cho `raw` và `clean`; sau đó so chênh lệch mAP50 với độ lệch giữa các seed. Nếu chênh lệch nằm trong nhiễu (test chỉ 100 ảnh), báo cáo là **chưa kết luận được**; các giả thuyết cần kiểm là ảnh trùng/rò rỉ test trong `raw`, nhãn máy còn sót trong `clean`, và box lỏng ở cả hai.

## 6. Quyết định và ghi chú AI

**(a) Quyết định cuối: Release** với 202 ảnh, 0 lỗi bắt buộc, 16/202 cảnh báo. Để giữ Release cần: (i) người xem nốt 16 ảnh còn cảnh báo + 22 ảnh ngoài ngân sách; (ii) nếu phát hiện thêm lỗi khiến tỉ lệ cảnh báo ≥ 10% thì chuyển **Hold**; (iii) nếu có lỗi bắt buộc mới thì **Rework**. Với lô dữ liệu khác phải calibrate lại, không bê nguyên conf 0,80.

**(b) AI:** Prompt chính: "đọc repo, giải thích luồng pipeline, viết 4 module theo docstring/test, chỉ được sửa 2 khoá CALIBRATE". Cách kiểm: đọc lại từng dòng code, chạy `pytest` theo từng module (79 pass), chạy pipeline rồi đối chiếu số trong CSV/JSON, grep để chắc chắn không đọc `data/test`. Một lần AI sai: demo `BOX_TINY` dùng box 0,02 × 480 = 9,6 px và bị báo lỗi; em tưởng code sai, nhưng thực ra demo sai ngưỡng 12 px — sửa demo thành 0,04 × 0,05.
