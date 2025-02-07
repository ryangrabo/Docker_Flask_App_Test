import os
import logging
from flask import Blueprint, render_template, jsonify, request, redirect, url_for
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from bson import ObjectId

bp = Blueprint("main", __name__)

# MongoDB connection details
MONGO_URI = "mongodb://my_mongo:27017/"
DATABASE_NAME = "seniorDesignTesting"
COLLECTION_NAME = "sendAndRecievePlantInfoTest"

# local/OneDrive folder for uploads:
UPLOAD_FOLDER = r"C:\Users\frost\OneDrive - The Pennsylvania State University\2024_drone_images\purple_loosestrife\07-17-2024"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"jpg", "jpeg"}

# (Optional) Offsets for EXIF usage or other logic:
LATITUDE_OFFSET = 0.00004
LONGITUDE_OFFSET = 0.00
AGL_OFFSET_FEET = -10  # Adjust to make AGL values ~20 feet

logging.basicConfig(level=logging.INFO)


def connect_to_mongodb():
    """Connects to MongoDB and returns a client."""
    client = MongoClient(MONGO_URI)
    # Quick test to ensure we can ping the server
    client.admin.command("ping")
    print("Connected successfully to MongoDB")
    return client


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@bp.route("/")
def index():
    """Render a simple landing page."""
    return render_template("index.html", mapbox_token=os.getenv("MAPBOX_TOKEN"))


@bp.route("/azuremapdemo")
def get_azure_map():
    """(Optional) Another demo page."""
    return render_template("AzureMapDemo.html", azuremap_token=os.getenv("AZUREMAP_TOKEN"))


import base64
from bson import ObjectId

@bp.route("/images")
def get_images():
    client = connect_to_mongodb()
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]

    docs = collection.find({})
    images = []

    for doc in docs:
        # Convert ObjectId to string if you want to return it
        doc_id = str(doc["_id"])

        # Get the raw binary (BSON Binary type)
        raw_image_data = doc.get("image_data")

        # Convert to base64 if available
        if raw_image_data:
            image_data_base64 = base64.b64encode(raw_image_data).decode('utf-8')
        else:
            image_data_base64 = None

        images.append({
            "_id": doc_id,
            "filename": doc.get("filename"),
            "lat": doc.get("lat"),
            "lon": doc.get("lon"),
            "yaw": doc.get("yaw"),
            "msl_alt": doc.get("msl_alt"),
            "agl": doc.get("agl"),
            "agl_feet": doc.get("agl_feet"),
            # Add the base64 field
            "image_data_base64": image_data_base64
        })

    client.close()
    return jsonify(images)


@bp.route("/upload", methods=["GET", "POST"])
def upload_file():
    """
    Upload JPG/JPEG files to a local folder. 
    (Optionally, you could modify or remove if you prefer only DB-based workflows.)
    """
    if request.method == "POST":
        if "file" not in request.files:
            return redirect(request.url)

        files = request.files.getlist("file")
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(UPLOAD_FOLDER, filename))
                logging.info(f"Uploaded file: {filename}")
        return redirect(url_for("main.index"))
    
    return render_template("upload.html")


@bp.route("/test-image")
def test_image():
    client = MongoClient(MONGO_URI)
    db = client["seniorDesignTesting"]
    collection = db["sendAndRecievePlantInfoTest"]

    doc = collection.find_one({"image_data": {"$exists": True}})
    
    if not doc:
        return jsonify({"error": "No images found in database"}), 404

    return jsonify({
        "_id": str(doc["_id"]),
        "filename": doc.get("filename"),
        "image_data": base64.b64encode(doc["image_data"]).decode("utf-8") if "image_data" in doc else None
    })
