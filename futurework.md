# C.O.R.E. Video Intelligence - Project Roadmap

This document serves as the unified checklist for the system's development, combining the original requirements with the Minutes of Meeting (MOM – June 2nd).

## 🚀 Pending Objectives (To-Do)

### 1. Investigation Module & Forensics
- [ ] **Image Enhancement:** Add a Super Resolution feature to programmatically enhance (zoom, crop, sharpen, smoothen) blurry images during forensic investigations before searching.
- [ ] **Direct Processing:** Allow operators to process and view these enhanced images directly from the investigation screen without external tools.
- [ ] **Search History Analysis:** Provide detailed report analysis of previous search history that can be exported to PDF and Excel.
- [ ] **Complex Filtering:** Add advanced filtering on reports (Date range, Multiple Cameras dropdown, Multiple Subjects, and a "Match Score %" slider).

### 2. Map View & Telemetry
- [ ] **Interactive Surat Map:** Display an interactive city map visualizing all camera locations based on their configured coordinates.
- [ ] **Camera Telemetry:** Allow users to interact with camera markers on the map to view specific telemetry and details.

### 3. NVR & Hardware Integration
- [ ] **System Monitoring:** Build a dashboard widget to monitor the host machine's average GPU and CPU utilization.

### 4. Watchlist Improvements
- [ ] **Anti-Duplication:** Implement a check during Face Enrollment to warn the user if they are trying to add a person who is already enrolled in the system.

---

## ✅ Completed Objectives

### Architecture & Enterprise Standards
- [x] **Complete UI Redesign:** Established a highly professional, modern, dark-mode appearance.
- [x] **Terminology Cleanup:** Stripped out confusing technical jargon (e.g., replaced "WebRTC" and "RTSP" with user-friendly terms).
- [x] **Database Architecture:** Migrated to a robust PostgreSQL setup (for metadata) alongside Milvus (for vector embeddings).
- [x] **RBAC (Role-Based Access Control):** Implemented multi-tier admin/user login systems.
- [x] **Enterprise Architecture Refactor:** Adopted SOLID principles and the Repository Pattern, completely decoupling SQL logic from FastAPI routes.
- [x] **12-Factor Compliance:** Migrated all hardcoded credentials and configuration into a secure `.env` file and central `config.py`.
- [x] **Observability Engine:** Replaced naked print statements with structured `loguru` logging across all asynchronous workers and eliminated silent failures.
- [x] **Defensive Programming:** Implemented strict Pydantic validation boundaries and exception obfuscation to prevent data leakage.

### Live Dashboard & Monitoring
- [x] **Active Target Panel:** Added a high-impact panel displaying the absolute latest detection side-by-side with their Watchlist reference image.
- [x] **Recent Detections Queue:** Built a real-time queue displaying the last 10 detections, replacing the legacy intel feed.
- [x] **Dynamic Routing:** Integrated Dynamic MediaMTX API Synchronization to automatically route RTSP streams when cameras are added.

### Watchlist & Face Enrollment
- [x] **Enrollment UI:** Created a dedicated system to enroll suspects with demographic details, tactical notes, and threat levels.
- [x] **Absolute Synchronization:** Fixed backend logic to instantly flush Milvus vectors to disk upon enrollment, ensuring targets are searchable in real-time.
- [x] **Ghost-Match Prevention:** Updated AI Workers to use strict database JOINs to ensure suspects belong to active watchlists before triggering alerts.
- [x] **Color Coding:** Added visual color coding to Watchlist categories.

### Camera & NVR Management
- [x] **Automated NVR Discovery:** Deployed an asynchronous ONVIF auto-scanner with a 4-state UI and concurrent ghost-channel validation.
- [x] **NVR Time Machine Integration:** Implemented targeted historical recording extraction via ISAPI/RTSP and `producer_historic.py` for Uniview NVRs.
- [x] **Editable Configs:** Enabled real-time editing of camera properties (including Latitude/Longitude fields).
- [x] **Active Health Checks:** Built live stream validation that automatically flags dead streams as "Offline".
- [x] **Interactive Layouts:** Implemented Drag-and-Drop (DND) functionality for the camera grid.

### Alerts & Notifications
- [x] **Threat Alert Modal:** Added real-time popups to instantly flag critical events to operators.
- [x] **System-Wide Alert Infrastructure:** Configured asynchronous SMTP Email integrations and persistent database storage for all generated alerts.
- [x] **Asynchronous SMS Engine:** Built a fully non-blocking Twilio SMS pipeline with 160-character cost protections, E.164 normalization, and Redis anti-spam TTL locks.

---
**Target Deadline:** 11th June 2026
