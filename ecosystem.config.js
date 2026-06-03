// ============================================================
// C.O.R.E. Video Intelligence - PM2 Process Manager Config
// Usage: pm2 start ecosystem.config.js
// ============================================================

// Dynamically resolve paths relative to THIS file's location
const path = require('path');
const PROJECT_ROOT = __dirname;
const VENV_PYTHON = path.join(PROJECT_ROOT, 'venv', 'bin', 'python');
const VENV_UVICORN = path.join(PROJECT_ROOT, 'venv', 'bin', 'uvicorn');

module.exports = {
  apps: [
    {
      name: "1-FastAPI-Backend",
      script: VENV_UVICORN,
      args: "newapi:app --host 0.0.0.0 --port 8000",
      cwd: path.join(PROJECT_ROOT, "backend_api"),
      interpreter: VENV_PYTHON,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 3000,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    },
    {
      name: "2-Camera-Ingestion",
      script: "producer.py",
      cwd: path.join(PROJECT_ROOT, "Ingestion"),
      interpreter: VENV_PYTHON,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    },
    {
      name: "3-Worker-YOLO",
      script: "worker_yolo.py",
      cwd: path.join(PROJECT_ROOT, "ai_worker"),
      interpreter: VENV_PYTHON,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    },
    {
      name: "4-Worker-Face",
      script: "worker_face.py",
      cwd: path.join(PROJECT_ROOT, "ai_worker"),
      interpreter: VENV_PYTHON,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    },
    {
      name: "5-Worker-Notify",
      script: "worker_notify.py",
      cwd: path.join(PROJECT_ROOT, "backend_api"),
      interpreter: VENV_PYTHON,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    },
    {
      name: "6-React-Frontend",
      script: "npm",
      args: "run dev -- --host 0.0.0.0",
      cwd: path.join(PROJECT_ROOT, "frontend"),
      autorestart: true,
      max_restarts: 5,
      restart_delay: 3000
    }
  ]
};