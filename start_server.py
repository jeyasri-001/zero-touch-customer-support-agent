#!/usr/bin/env python3
"""
Simple script to start the FastAPI server
"""

import uvicorn

if __name__ == "__main__":
    print("🚀 Starting Zero-Touch Agent API...")
    print("📡 Server will run at: http://localhost:8000")
    print("📊 Dashboard will be at: http://localhost:8501 (start separately)")
    print("\nPress Ctrl+C to stop\n")
    
    # Only watch app/ and data/ - prevents dashboard changes from triggering reload
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app", "data"],
    )
