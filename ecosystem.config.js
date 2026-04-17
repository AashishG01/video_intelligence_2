module.exports = {
  apps: [
    {
      name: "1-FastAPI-Backend",
      // Uvicorn file ka absolute path
      script: "/home/user/Desktop/Video Surveillence ETE/venv/bin/uvicorn", 
      args: "newapi:app --host 0.0.0.0 --port 8000",
      cwd: "/home/user/Desktop/Video Surveillence ETE/backend_api",
      // Python interpreter ka absolute path
      interpreter: "/home/user/Desktop/Video Surveillence ETE/venv/bin/python",
      autorestart: true
    },
    {
      name: "2-Camera-Ingestion",
      script: "producer.py",
      cwd: "/home/user/Desktop/Video Surveillence ETE/Ingestion",
      interpreter: "/home/user/Desktop/Video Surveillence ETE/venv/bin/python",
      autorestart: true,
    },
    {
      name: "3-Worker-YOLO",
      script: "worker_yolo.py",
      cwd: "/home/user/Desktop/Video Surveillence ETE/ai_worker",
      interpreter: "/home/user/Desktop/Video Surveillence ETE/venv/bin/python",
      autorestart: true,
    },
    {
      name: "4-Worker-Face",
      script: "worker_face.py",
      cwd: "/home/user/Desktop/Video Surveillence ETE/ai_worker",
      interpreter: "/home/user/Desktop/Video Surveillence ETE/venv/bin/python",
      autorestart: true,
    },
    {
      name: "5-React-Frontend",
      script: "npm",
      args: "run dev",
      cwd: "/home/user/Desktop/Video Surveillence ETE/frontend",
      autorestart: true
    }
  ]
};