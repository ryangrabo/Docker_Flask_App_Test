import os
from flask import Flask

def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv('SECRET_KEY')
    
    UPLOAD_FOLDERS = [
      #going to be database connection
    ]
    for folder in UPLOAD_FOLDERS:
        os.makedirs(folder, exist_ok=True)

    from .routes import bp as main_bp
    app.register_blueprint(main_bp)

    return app
