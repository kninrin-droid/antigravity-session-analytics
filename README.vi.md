<div align="center">

# Antigravity Session Analytics (Phân tích Session)

**Theo dõi chi phí, token, cache, ngữ cảnh và điểm tối ưu trực tiếp cho phiên hội thoại đang mở ngay trong khung bên phải Antigravity.**

[![Python 3](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](#cài-đặt-nhanh)
[![Node.js](https://img.shields.io/badge/Sidecar-Node.js-339933?logo=nodedotjs&logoColor=white)](#cách-hoạt-động)
[![Zero Dependencies](https://img.shields.io/badge/Thư%20viện%20ngoài-Không%20cần-10b981)](#cách-hoạt-động)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[English](README.md) · [Tiếng Việt](README.vi.md)

</div>

---

Plugin giao diện độc lập cho **Google Antigravity**, tự động nhận diện **đúng cuộc hội thoại đang mở** để phân tích theo thời gian thực — không cần mở cổng phụ, không quét nền, không cần cài thêm thư viện ngoài.

### Tính năng chính

- **Điểm tối ưu phiên (0–100):** Tự động khuyến nghị (*Mới bắt đầu / Tiếp tục / Sắp tới hạn / Nên tạo mới*) dựa trên độ phình ngữ cảnh, tỷ lệ trúng cache gần đây, tốc độ nạp token mới và độ sâu hội thoại.
- **Chi phí & Tiết kiệm Cache:** Ước tính chi phí USD + VNĐ tách rõ **Input mới**, **Cache đọc** và **Output**, kèm số tiền tiết kiệm được nhờ cache.
- **Biểu đồ cột chồng 3 màu:** Mỗi bước hiển thị cột chồng **Input mới** (xanh dương) · **Cache** (xanh lá) · **Output** (tím) cùng đường tăng trưởng **Ngữ cảnh** (cam). Rê chuột xem số liệu chi tiết, bấm cột để nhảy thẳng tới hóa đơn bước đó.
- **Chi tiết Từng bước / Lượt hỏi / Model & Tool:** Hiện sẵn `In / Cache / Out` và chênh lệch ngữ cảnh (`Δ`) trên từng bước, bấm mở rộng xem hóa đơn, tổng hợp chi phí theo từng câu hỏi và xuất file **CSV** chỉ với 1 nút bấm.
- **Nhẹ & ăn theo giao diện Antigravity:** Tự đổi theo theme Sáng/Tối của Antigravity và lưu đệm theo `mtime:size` của `transcript.jsonl` (phản hồi dưới 2 ms khi file chưa đổi).

## Cài đặt nhanh

Yêu cầu **Google Antigravity** và **Python 3** có sẵn trong `PATH` (`python`, `py`, hoặc `python3`).

```powershell
# Windows (PowerShell)
git clone https://github.com/kninrin-droid/antigravity-session-analytics.git "$HOME\.gemini\config\plugins\antigravity-session-analytics"
```

```bash
# macOS / Linux
git clone https://github.com/kninrin-droid/antigravity-session-analytics.git ~/.gemini/config/plugins/antigravity-session-analytics
```

Sau đó khởi động lại Antigravity (hoặc bật plugin trong **Customizations → Installed**) rồi bấm dấu `+` ở khung bên phải chọn **Phân tích Session**.

## Cách hoạt động

<details>
<summary>Cấu trúc thư mục & chạy kiểm thử</summary>

```text
antigravity-session-analytics/
├── plugin.json                    # Khai báo plugin Antigravity
├── assets/logo.svg                # Biểu tượng plugin
├── sidecars/stats/
│   ├── sidecar.json               # Đăng ký khung bên phải (AUX_PANE)
│   ├── package.json               # Khai báo ES Module
│   ├── main.mjs                   # Backend Node nhẹ (cache theo mtime:size)
│   ├── session_analyzer.py        # Bộ phân tích transcript.jsonl thuần Python chuẩn
│   └── index.html                 # Giao diện khung bên phải tự chứa
└── tests/
    └── test_session_analyzer.py   # Bộ test tự động (Python stdlib)
```

- Chỉ đọc (read-only) file `~/.gemini/antigravity/brain/<conversationId>/.system_generated/logs/transcript.jsonl` (hỗ trợ thêm `antigravity-cli/brain/`).
- Không gửi dữ liệu ra mạng, không mở cổng mạng ngoài cầu nối sidecar mặc định của Antigravity.

### Chạy kiểm thử

```bash
python -m unittest discover -s tests -v
```

</details>

## Giấy phép

[MIT](LICENSE)
