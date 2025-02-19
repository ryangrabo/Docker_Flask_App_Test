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
from flask import request, jsonify, render_template
from ultralytics import YOLO
import os
import time
import cv2
import numpy as np
from werkzeug.utils import secure_filename
from io import BytesIO
from PIL import Image
import logging
import gridfs

bp = Blueprint("main", __name__)



# Use the Docker service name when running inside Docker
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

DATABASE_NAME = "seniorDesignTesting"
COLLECTION_NAME = "sendAndRecievePlantInfoTest"

#file storage system for mongo
client = MongoClient(MONGO_URI)  # Connect to MongoDB
db = client[DATABASE_NAME]  # Get database instance
fs = gridfs.GridFS(db)  

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

#MAPBOX

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
                "predicted_class": properties.get("predicted_class"),
                "probabilities": properties.get("probabilities"),
                "file_id": properties.get("file_id")
            },
            "geometry": {
                "type": "Point",
                "coordinates": [properties.get("lon"), properties.get("lat")]
            }
        }

        geojson_data["features"].append(feature)

    return jsonify(geojson_data)


@bp.route("/getImage/<file_id>", methods=["GET"])
def get_image(file_id):
    """Retrieve and serve an image stored in MongoDB GridFS."""
    try:
        # Convert file_id from string to ObjectId
        file_object_id = ObjectId(file_id)

        # Retrieve the image from GridFS
        retrieved_file = fs.get(file_object_id)

        return send_file(BytesIO(retrieved_file.read()), mimetype="image/jpeg")

    except Exception as e:
        return jsonify({"error": f"Image not found: {str(e)}"}), 404




@bp.route("/runInferenceTest", methods=["GET", "POST"])
def run_inference():
    if request.method == "GET":
        return render_template("runInference.html")
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)

        # Save file to MongoDB GridFS
        file_id = fs.put(file, filename=filename)
        print(f"Saved to MongoDB with ID: {file_id}")

        # Retrieve the image from MongoDB
        retrieved_file = fs.get(file_id)
        image_data = np.array(Image.open(BytesIO(retrieved_file.read())))  # Convert to NumPy array
        image_data = cv2.cvtColor(image_data, cv2.COLOR_RGB2BGR)  # Convert RGB to BGR

        start_time = time.perf_counter()
        # Get model
        model_path = os.path.join(os.getcwd(), "app", "singleModel_0.0.1.pt")
        model = YOLO(model_path)
        # Run YOLO inference
        results = model.predict(image_data, stream=True)
        results_list = []

        for result in results:
            top_index = result.probs.top1  # Get top prediction index
            top_class = result.names[top_index]  # Get class name
            probabilities = result.probs.data.tolist()  # Get probabilities

            results_list.append({
                "filename": filename,
                "predicted_class": top_class,
                "probabilities": probabilities,
                "top_index": top_index,
                "file_id": str(file_id)  # Store MongoDB file ID
            })

        end_time = time.perf_counter()
        elapsed_time = round(end_time - start_time, 4)

        return jsonify({
            "results": results_list,
            "elapsed_time": elapsed_time
        })

@bp.route("/saveResults", methods=["POST"])
def save_results():
    client = connect_to_mongodb()
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]

    data = request.json
    results = data.get("results", [])

    if not results:
        return jsonify({"error": "No results provided"}), 400

    geojson_results = []

    for result in results:
        try:
            # Retrieve image file from MongoDB GridFS
            retrieved_file = fs.get(ObjectId(result["file_id"]))  # Convert file_id to ObjectId
            file_bytes = retrieved_file.read()

            # Extract EXIF metadata
            stream = BytesIO(file_bytes)
            tags = exifread.process_file(stream, details=False)

            # Extract GPS data
            lat, lon = None, None
            if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
                lat = convert_to_degrees(tags['GPS GPSLatitude'], tags.get('GPS GPSLatitudeRef'))
                lon = convert_to_degrees(tags['GPS GPSLongitude'], tags.get('GPS GPSLongitudeRef'))
                lat = lat - LATITUDE_OFFSET if lat is not None else None
                lon = lon - LONGITUDE_OFFSET if lon is not None else None

            # Extract image direction (yaw) if available
            yaw = "Unknown"
            if 'GPS GPSImgDirection' in tags:
                try:
                    direction = tags['GPS GPSImgDirection'].values[0]
                    yaw = float(direction.num) / float(direction.den)
                except Exception:
                    yaw = "Unknown"

            # Extract altitude (meters) if available
            altitude_meters = None
            if 'GPS GPSAltitude' in tags:
                try:
                    altitude = tags['GPS GPSAltitude'].values[0]
                    altitude_meters = float(altitude.num) / float(altitude.den)
                except Exception:
                    altitude_meters = None

            # Create GeoJSON formatted result
            geojson_results.append({
                "type": "Feature",
                "properties": {
                    "filename": result["filename"],
                    "predicted_class": result["predicted_class"],
                    "probabilities": result["probabilities"],
                    "file_id": result["file_id"],
                    "lat": lat,
                    "lon": lon,
                    "yaw": yaw,
                    "msl_alt": altitude_meters,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat] if lat is not None and lon is not None else None
                }
            })

        except Exception as e:
            logging.error(f"Error processing file {result['file_id']}: {e}")

    # Save results in MongoDB
    if geojson_results:
        inserted_ids = collection.insert_many(geojson_results).inserted_ids
        return jsonify({"message": f"Saved {len(inserted_ids)} results to the database"})

    return jsonify({"error": "No valid results to save"}), 400



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
