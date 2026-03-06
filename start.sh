#!/bin/bash
set -e

echo "=== AI Agent Team Orchestrator ==="
echo ""

# Check .env
if [ ! -f backend/.env ]; then
    echo "Creating backend/.env from template..."
    cp backend/.env.example backend/.env
    echo "⚠️  Please set your ANTHROPIC_API_KEY in backend/.env before starting."
    echo ""
fi

# Start Redis (if not running)
if ! redis-cli ping &>/dev/null; then
    echo "Starting Redis..."
    redis-server --daemonize yes --loglevel warning
    sleep 1
fi

# Backend
echo "Starting backend (FastAPI)..."
cd backend
if [ ! -d .venv ]; then
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt -q
fi
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!
cd ..

# Frontend
echo "Starting frontend (Next.js)..."
cd frontend
if [ ! -d node_modules ]; then
    npm install -q
fi
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ Services started:"
echo "   Backend:  http://localhost:8000"
echo "   Frontend: http://localhost:3000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services."

trap "kill 0; exit" SIGINT SIGTERM

wait
