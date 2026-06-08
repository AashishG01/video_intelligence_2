# C.O.R.E. — NVR Integration Handoff
## Uniview (UNV) NVR — Verified Reference Document

---

## 1. NVR Device Details

| Field | Value |
|---|---|
| Brand | Uniview (UNV) |
| IP Address | 172.16.0.160 |
| RTSP Port | 554 |
| Username | admin |
| Password | Admin@123 |
| URL-encoded password | Admin%40123 |
| Channels confirmed | c1, c2 |
| Video codec | HEVC / H.265 (Main profile) |
| Resolution | 720 × 576 |
| Frame rate | 25 fps |
| Stream server | ONVIF RTSP Server |

> The `@` in the password must always be written as `%40` inside RTSP URLs.
> `Admin@123` → `Admin%40123`

---

## 2. Live Stream URLs

### Pattern
```
rtsp://admin:Admin%40123@172.16.0.160:554/unicast/c{channel}/s1/live
```
`s1` = sub-stream (AI-friendly, lower resolution)
`s0` = main stream (full quality, use for recording only)

### Confirmed Working
```
Channel 1:
rtsp://admin:Admin%40123@172.16.0.160:554/unicast/c1/s1/live

Channel 2:
rtsp://admin:Admin%40123@172.16.0.160:554/unicast/c2/s1/live
```

### Quick Test (run on Ubuntu machine)
```bash
ffprobe -rtsp_transport tcp \
  "rtsp://admin:Admin%40123@172.16.0.160:554/unicast/c1/s1/live"
```
Expected: stream opens, shows `hevc`, `720x576`, `25 fps`

---

## 3. Historical Playback URLs

### Pattern
```
rtsp://admin:Admin%40123@172.16.0.160:554/c{channel}/b{unix_start}/e{unix_end}/replay
```

`b` = begin timestamp (Unix epoch, seconds)
`e` = end timestamp (Unix epoch, seconds)

### How to Get Unix Timestamps

**On Ubuntu terminal:**
```bash
# Example: 5 June 2026, 10:00 AM to 11:00 AM
date -d "2026-06-05 10:00:00" +%s    # → 1780653600
date -d "2026-06-05 11:00:00" +%s    # → 1780657200
```

**In Python:**
```python
from datetime import datetime

start = int(datetime(2026, 6, 5, 10, 0, 0).timestamp())
end   = int(datetime(2026, 6, 5, 11, 0, 0).timestamp())
```

### Example Playback URL
```
rtsp://admin:Admin%40123@172.16.0.160:554/c1/b1780653600/e1780657200/replay
```

### Quick Test
```bash
ffplay -rtsp_transport tcp \
  "rtsp://admin:Admin%40123@172.16.0.160:554/c1/b1780653600/e1780657200/replay"
```

---

## 4. URL Builder Reference

For any channel and any time range:

```python
def build_unv_live_url(channel: int) -> str:
    return (
        f"rtsp://admin:Admin%40123"
        f"@172.16.0.160:554"
        f"/unicast/c{channel}/s1/live"
    )

def build_unv_replay_url(channel: int, start_dt, end_dt) -> str:
    start_ts = int(start_dt.timestamp())
    end_ts   = int(end_dt.timestamp())
    return (
        f"rtsp://admin:Admin%40123"
        f"@172.16.0.160:554"
        f"/c{channel}/b{start_ts}/e{end_ts}/replay"
    )
```

---

## 5. Known Warnings (Not Errors)

When connecting, FFmpeg/OpenCV may print:

```
PPS id out of range
Error parsing NAL unit #0
Could not find ref with POC 8
missing picture in access unit
```

These are harmless. They appear because:
- Connection starts mid-GOP (mid-recording segment)
- Ubuntu 18.04 ships with FFmpeg 3.4 (older H.265 parser)
- UNV's H.265 stream implementation triggers these on connect

The stream recovers within the first few frames. No action needed.

---

## 6. Critical: Time Synchronization

Playback accuracy depends entirely on the NVR clock matching real time.

If the NVR clock is wrong, a request for `10:00 AM` plays back the wrong footage.

### Verify before using historical search:

```bash
# Check Ubuntu machine time
date

# Check NVR time via web interface
# Open browser → http://172.16.0.160 → login → System → Time settings
```

Both must show the same time. If they differ:
- Set NVR to sync via NTP in its web interface
- Or manually correct the NVR clock under System → Time

---

## 7. Integration into C.O.R.E. Pipeline

### Live
```
UNV NVR (172.16.0.160)
  ↓  RTSP /unicast/c{N}/s1/live
producer_nvr.py
  ↓  raw_frames_queue (Redis)
worker_yolo.py
  ↓  face_ready_queue (Redis)
worker_face_dual.py --mode live
  ↓
Milvus + PostgreSQL + Dashboard
```

### Historical
```
UNV NVR (172.16.0.160)
  ↓  RTSP /c{N}/b{start}/e{end}/replay
producer_historic.py --mode rtsp
  ↓  historic_frames_queue (Redis)
worker_face_dual.py --mode historic
  ↓
Milvus (historic collection) + PostgreSQL + Investigator View
```

### Database registration (one-time per channel)
```sql
INSERT INTO cameras (
    camera_id, camera_name, place,
    rtsp_url, fps_limit, is_active,
    nvr_brand, nvr_ip, nvr_user, nvr_pass, nvr_channel
) VALUES (
    'UNV01_CH01', 'UNV Channel 1', 'Location Name',
    NULL, 1, TRUE,
    'uniview', '172.16.0.160', 'admin', 'Admin@123', 1
);
```
`rtsp_url = NULL` tells the producer to auto-build the URL from `nvr_brand`, `nvr_ip`, and `nvr_channel`.

---

## 8. What Has Been Verified

- [x] NVR reachable at 172.16.0.160 over LAN
- [x] Channel 1 live stream opens and plays
- [x] Channel 2 live stream opens and plays
- [x] HEVC / H.265 codec confirmed
- [x] 720×576 @ 25fps confirmed
- [x] Replay URL pattern confirmed working
- [x] Unix timestamp format for b/e parameters confirmed
- [ ] Channel 3+ (not yet tested — discover by incrementing channel number)
- [ ] NVR clock vs Ubuntu clock sync (must verify before using historical search)
- [ ] Replay URL tested end-to-end with actual recording
