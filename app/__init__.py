"""
Application Factory
Creates and configures the Flask application
"""
from flask import Flask
from app.config import get_config
from app.extensions import db, socketio
import pytz


def create_app(config_name=None):
    """
    Application factory pattern
    Creates and configures Flask app
    """
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    
    # Load configuration
    if config_name:
        from app.config import config
        app.config.from_object(config[config_name])
    else:
        app.config.from_object(get_config())
    
    # Initialize extensions
    db.init_app(app)
    socketio.init_app(
        app,
        cors_allowed_origins=app.config['SOCKETIO_CORS_ALLOWED_ORIGINS'],
        async_mode=app.config['SOCKETIO_ASYNC_MODE']
    )
    
    # Add pytz to Jinja globals (for template compatibility)
    app.jinja_env.globals['pytz'] = pytz
    
    # Register blueprints
    from app.routes import auth_bp, admin_bp, student_bp
    
    # Auth routes (no prefix)
    app.register_blueprint(auth_bp)
    
    # Admin routes (prefixed with /admin)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    # Student routes (FIXED: Add /student prefix)
    app.register_blueprint(student_bp, url_prefix='/student')
    
    from app.routes.public import public_bp
    app.register_blueprint(public_bp)

    
    # Register Socket.IO events
    from app.sockets import register_socket_events
    with app.app_context():
        register_socket_events()
    
    # Create database tables
    with app.app_context():
        db.create_all()
        print('>>> Database tables created/verified')
    
    return app