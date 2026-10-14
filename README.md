# 🏋️‍♂️ HULK GYM - Smart Gym Management & AI Face Recognition System

A modern, high-performance Gym Management System built with **Django 5**, **OpenCV AI Face Recognition**, and a streamlined responsive UI.

---

## ✨ Key Features

- 👤 **AI Face Recognition Gate**:
  - Live continuous face detection and recognition using OpenCV DNN (`face_detection_yunet` + `face_recognition_sface`).
  - Active-first tiered search algorithm for sub-millisecond matching.
  - Multi-pose 5-angle enrollment with duplicate prevention.
  - Full-screen real-time visual alerts for active entry, expiring memberships, and expired subscriptions.

- 💳 **Memberships & Subscriptions**:
  - Flexible recurring plans (Monthly, Quarterly, Annual, Custom sessions).
  - Automated expiration tracking and renewal workflows.
  - Financial records, invoice receipts, and transaction history.

- 💬 **WhatsApp Automation**:
  - Native WhatsApp Web integration for automated welcome messages, renewal reminders, and subscription receipts.

- 💰 **Salaries & Staff Advances Management**:
  - Straightforward salary tracking with manager permission-based deductions/advances that automatically reconcile without messing up gym finances.

- 🔄 **One-Click Live GitHub Updater**:
  - In-app 1-click update button with automatic pre-update database snapshots (`backups/`).
  - Terminal-like execution feed with seamless migration application and face cache refresh.

- 📦 **100% Self-Contained Portable Client Distribution**:
  - Standalone build script (`build_dist.py`) that bundles an isolated Python 3.11 runtime so the entire gym system runs on any client Windows laptop with zero dependencies.

---

## 🚀 Quick Start (Development)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/mostafa-donia/hulk-gym.git
   cd hulk-gym/web_face
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize database & default settings:**
   ```bash
   python manage.py migrate
   python manage.py setup_gym --name "HULK GYM" --color "#84CC16"
   ```

5. **Start server:**
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

---

## 🛠️ Standalone Portable Packaging

To build a zero-dependency client package for distribution:
```bash
python build_dist.py
```
Output folder will be created at `dist/HULK_GYM` ready to be copied to any Windows PC.

---

## 📄 License
Proprietary - Developed by Eng. Mostafa Donia.
