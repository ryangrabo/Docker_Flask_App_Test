from app import create_app
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

app = create_app()

if __name__ == "__main__":
    app.run(host="localhost", port=5000)
