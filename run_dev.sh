#!/bin/bash

# Parrot Script - Development Runner
# Starts both Backend (FastAPI) and Frontend (Vite)

# Colors for better visibility
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🦜 Starting Parrot Script Development Environment...${NC}"

# 1. Backend Setup
echo -e "${GREEN}-> Starting Backend (FastAPI)...${NC}"
PYTHON_BIN="python3"
if [ -d ".venv" ]; then
    PYTHON_BIN=".venv/bin/python"
    echo "   Using virtual environment: $PYTHON_BIN"
fi

# Start backend in the background
export PYTHONPATH=$PYTHONPATH:.
$PYTHON_BIN -m uvicorn backend.api.server:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# 2. Frontend Setup
echo -e "${GREEN}-> Starting Frontend (Vite)...${NC}"
if [ -d "frontend" ]; then
    # Start frontend in the background
    cd frontend && npm run dev &
    FRONTEND_PID=$!
    cd ..
else
    echo "❌ Error: 'frontend' directory not found."
    kill $BACKEND_PID
    exit 1
fi

# Cleanup function to kill background processes on exit
cleanup() {
    echo -e "\n${BLUE}🛑 Stopping services...${NC}"
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    echo -e "${GREEN}Done.${NC}"
    exit
}

# Trap SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

echo -e "\n${BLUE}🚀 Services are starting!${NC}"
echo -e "   - Backend:  ${GREEN}http://127.0.0.1:8000${NC}"
echo -e "   - Frontend: ${GREEN}http://127.0.0.1:5173${NC}"
echo -e "\nPress ${BLUE}CTRL+C${NC} to stop both services."

# Wait for background processes
wait
