#!/usr/bin/env python3
"""
Conduit Service Runner
Convenience script to run the Conduit FastAPI application
"""

import uvicorn
import sys
import os
from config import settings

def main():
    """Main entry point for running the application"""
    
    # Check if .env file exists
    if not os.path.exists('.env'):
        print("❌ .env file not found!")
        print("📝 Please copy .env.example to .env and configure your Supabase credentials")
        print("🔧 cp .env.example .env")
        sys.exit(1)
    
    print(f"🚀 Starting {settings.app_name} v{settings.app_version}")
    print(f"🌍 Environment: {'Development' if settings.debug else 'Production'}")
    print(f"📡 Server will be available at: http://localhost:8000")
    print(f"📚 API Documentation: http://localhost:8000/docs")
    
    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=settings.debug,
            log_level="info" if settings.debug else "warning",
            access_log=settings.debug
        )
    except KeyboardInterrupt:
        print("\n👋 Shutting down Conduit service...")
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
