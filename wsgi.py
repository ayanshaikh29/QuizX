"""
Production WSGI Entry Point
Used by gunicorn and other WSGI servers
"""
import os
from app import create_app
from app.extensions import socketio

# Create Flask app
app = create_app()

# For development server
if __name__ == '__main__':
    # Development mode only
    # In production, use: gunicorn --worker-class eventlet -w 1 wsgi:app
    port = int(os.getenv('PORT', 5000))
    
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=True,
        use_reloader=False  # Fix for Windows + Python 3.13 compatibility
    )