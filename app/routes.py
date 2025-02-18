import os
import logging
import base64
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, send_file, abort, Flask, Response
from werkzeug.utils import secure_filename
from pymongo import MongoClient
import pymongo
from bson import ObjectId, Binary
import exifread
from io import BytesIO  # Ensure BytesIO is imported
import io
import socket

bp = Blueprint("main", __name__)



# Use the Docker service name when running inside Docker
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

DATABASE_NAME = "seniorDesignTesting"
COLLECTION_NAME = "sendAndRecievePlantInfoTest"




# Local/OneDrive folder for uploads:
UPLOAD_FOLDER = r"C:\Users\frost\OneDrive - The Pennsylvania State University\2024_drone_images\purple_loosestrife\07-17-2024"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"jpg", "jpeg"}

# Offsets for drone error:
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


def convert_to_degrees(value, ref_tag):
    """
    Converts the GPS coordinates stored in the EXIF to degrees in float format.
    :param value: EXIF GPS coordinate value.
    :param ref_tag: EXIF GPS reference tag (e.g., 'N', 'S', 'E', 'W').
    :return: GPS coordinate in degrees (float) or None if conversion fails.
    """
    try:
        d = value.values[0].num / value.values[0].den
        m = value.values[1].num / value.values[1].den
        s = value.values[2].num / value.values[2].den
        result = d + (m / 60.0) + (s / 3600.0)
        if ref_tag and ref_tag.values[0] in ['S', 'W']:
            result = -result
        return result
    except Exception as e:
        logging.error(f"Error converting GPS value: {e}")
        return None


@bp.route("/")
def index():
    """Render a simple landing page."""
    return render_template("mapbox.html", mapbox_token=os.getenv("MAPBOX_TOKEN"))
    #return render_template("index.html", mapbox_token=os.getenv("MAPBOX_TOKEN"))

@bp.route('/images')
def get_images():
    """Fetches image data from MongoDB and returns it as a GeoJSON FeatureCollection."""
    client = connect_to_mongodb()
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]

    docs = collection.find({})
#start the geojson data
    geojson_data = {
        "type": "FeatureCollection",
        "features": []
    }

    for doc in docs:
        # Convert ObjectId to string so that mapbox had a marker id for the point for clustering
        doc_id = str(doc["_id"])

        # Access the 'properties' dictionary correctly
        properties = doc.get("properties", {})

        # Extract image binary data if available
        raw_image_data = properties.get("image_data_binary")
        image_data_base64 = None

        if raw_image_data and isinstance(raw_image_data, dict) and "$binary" in raw_image_data:
            image_data_base64 = raw_image_data["$binary"]["base64"]

        # Create a valid GeoJSON feature
        feature = {
            "type": "Feature",
            "properties": {
                "_id": doc_id,
                "filename": properties.get("filename"),
                "lat": properties.get("lat"),
                "lon": properties.get("lon"),
                "yaw": properties.get("yaw"),
                "msl_alt": properties.get("msl_alt"),
                "agl": properties.get("agl", "undefined"),
                "agl_feet": properties.get("agl_feet", "undefined"),
                # Include base64 image data
                "image_data_base64": image_data_base64
            },
            "geometry": {
                "type": "Point",
                "coordinates": [properties.get("lon"), properties.get("lat")]
            }
        }

        geojson_data["features"].append(feature)

    return jsonify(geojson_data)

@bp.route("/get_image/<image_id>")
def get_image(image_id):
    client = connect_to_mongodb()
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]
    """Fetch image stored in base64 format from MongoDB."""
    try:
        logging.info(f"Retrieving image with ID: {image_id}")
        image_doc = collection.find_one({"_id": ObjectId(image_id)})

        if not image_doc or "image_data" not in image_doc["properties"]:
            logging.error("Image not found in MongoDB.")
            return abort(404, "Image not found")

        image_data = image_doc["properties"]["image_data"]  # BSON Binary

        # Ensure it's in correct binary format
        if not isinstance(image_data, bytes):
            logging.error("Stored image is not in bytes format.")
            return abort(500, "Invalid image format")

        logging.info("Successfully retrieved image from MongoDB.")
        return Response(image_data, mimetype="image/jpeg")

    except Exception as e:
        logging.error(f"Error retrieving image {image_id}: {e}")
        return abort(500)

@bp.route("/upload", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        if "file" not in request.files:
            logging.error(" No file part in request")
            return redirect(request.url)

        files = request.files.getlist("file")
        client = connect_to_mongodb()
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]

        # # Log database and collection being used
        logging.info(f" Writing to database: {db.name}")
        logging.info(f" Writing to collection: {collection.name}")
        logging.info(f" Document count before upload: {collection.count_documents({})}")
        logging.info(f" Flask is connecting to: {os.getenv('MONGO_URI', 'mongodb://localhost:27017/')}")            
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)

                # Read file bytes into memory
                file_bytes = file.read()

                # Create a BytesIO stream for EXIF processing
                stream = BytesIO(file_bytes)
                tags = exifread.process_file(stream, details=False)

                # Extract GPS data
                if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
                    lat = convert_to_degrees(tags['GPS GPSLatitude'], tags.get('GPS GPSLatitudeRef'))
                    lon = convert_to_degrees(tags['GPS GPSLongitude'], tags.get('GPS GPSLongitudeRef'))
                    # Apply offsets if needed
                    lat = lat - LATITUDE_OFFSET if lat is not None else None
                    lon = lon - LONGITUDE_OFFSET if lon is not None else None
                else:
                    lat, lon = None, None

                # Extract image direction (yaw) if available
                if 'GPS GPSImgDirection' in tags:
                    try:
                        direction = tags['GPS GPSImgDirection'].values[0]
                        yaw = float(direction.num) / float(direction.den)
                    except Exception:
                        yaw = "Unknown"
                else:
                    yaw = "Unknown"

                # Extract altitude (meters) if available
                if 'GPS GPSAltitude' in tags:
                    try:
                        altitude = tags['GPS GPSAltitude'].values[0]
                        altitude_meters = float(altitude.num) / float(altitude.den)
                    except Exception:
                        altitude_meters = None
                else:
                    altitude_meters = None

                image_metadata = {
                            "type": "Feature",
                            "properties": {
                            "filename": filename,
                            "lat": lat,
                            "lon": lon,
                            "yaw": yaw,
                            "msl_alt": altitude_meters,
                            "image_data_base64": Binary(file_bytes)
                            },
                            "geometry": {
                                "type": "Point",
                                "coordinates": [lon, lat]
                            }
                        }
                # Insert into MongoDB
                result = collection.insert_one(image_metadata)
                logging.info(f" Inserted document with id: {result.inserted_id}")

        # Check if the document was successfully inserted
        logging.info(f" Document count after upload: {collection.count_documents({})}")
        sample_doc = collection.find_one({}, {"_id": 1, "properties.filename": 1, "properties.lat": 1, "properties.lon": 1})
        logging.info(f"Sample document (without binary): {sample_doc}")


        client.close()
        return redirect(url_for("main.index"))

    return render_template("testUpload.html")

#testing yolomodel shi
from ultralytics import YOLO
import time

@bp.route("/runInferenceTest", methods=["GET", "POST"])
def run_inference():
    if request.method == "POST":
        if "file" not in request.files:
            logging.error(" No file part in request")
            return redirect(request.url)

        files = request.files.getlist("file")
                
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)

                # Read file bytes into memory
                file_bytes = file.read()
                # Load the model
                model = YOLO("singleModel_0.0.1.pt")  # Load a pretrained model in same directory as routes
                start_time=time.perf_counter()
                
        return redirect(url_for("main.index"))

    return render_template("runInference.html")

@bp.route("/test-image")
def test_image():
    client = connect_to_mongodb()
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]

    doc = collection.find_one()
    
    if not doc:
        return jsonify({"error": "No images found in database"}), 404

    return jsonify({
        "_id": str(doc["_id"]),
        "filename": doc.get("filename"),
        "image_data": base64.b64encode(doc["image_data"]).decode("utf-8") if "image_data" in doc else None
    })
