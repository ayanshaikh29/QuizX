"""
Flask Extensions
Centralized extension initialization
"""
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

# Initialize extensions (without app binding)
db = SQLAlchemy()
socketio = SocketIO()

# Global state dictionaries (will be managed by services)
quiz_state = {}
active_participants = {}