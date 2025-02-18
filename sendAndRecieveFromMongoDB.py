from pymongo import MongoClient
from bson import Binary  # For storing raw bytes in MongoDB
import os
import exifread
import logging
import socket

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Use 'mongodbtest' if running inside Docker, otherwise use 'localhost'
MONGO_HOST = "mongodbtest" if socket.gethostname() == "flask_app" else "localhost"
MONGO_URI = f"mongodb://{MONGO_HOST}:27017/"

DATABASE_NAME = "seniorDesignTesting"
COLLECTION_NAME = "sendAndRecievePlantInfoTest"

# Define the upload folder
UPLOAD_FOLDERS = r"C:\Users\frost\OneDrive - The Pennsylvania State University\DRONES ONLY\2024_drone_images"
#UPLOAD_FOLDERS = r"/home/landon/Senior-Design/Training"

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDERS, exist_ok=True)

# Offsets for GPS
LATITUDE_OFFSET = 0.00004
LONGITUDE_OFFSET = 0.00
AGL_OFFSET_FEET = -10
ALLOWED_EXTENSIONS = {'jpg', 'jpeg'}

def allowed_file(filename):
    """Check if the file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def connect_to_mongodb():
    """Connects to MongoDB and verifies the connection."""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)  # Increased timeout
        client.admin.command("ping")
        logging.info("Connected successfully to MongoDB.")
        return client
    except Exception as e:
        logging.error(f"MongoDB connection failed: {e}")
        raise Exception("Error connecting to MongoDB.") from e

def insert_image_metadata(collection, metadata):
    """Insert a single document into MongoDB."""
    try:
        result = collection.insert_one(metadata)
        logging.info(f"Inserted document with id: {result.inserted_id}")
    except Exception as e:
        logging.error(f"Error inserting metadata: {e}")
        raise Exception("Error inserting metadata.") from e

from bson import Binary  # For storing binary data in MongoDB

def process_image(filepath):
    """Extract metadata and return a GeoJSON feature dictionary with image in binary."""
    try:
        if not os.path.exists(filepath):
            logging.error(f"File not found: {filepath}")
            return None

        print(f"Opening file: {filepath}")

        with open(filepath, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            image_bytes = f.read()  # Read image as binary

        lat, lon = extract_gps(tags)
        yaw = extract_yaw(tags)
        altitude_meters = extract_altitude(tags)

        return {
            "type": "Feature",
            "properties": {
                "filename": os.path.basename(filepath),
                "lat": lat,
                "lon": lon,
                "msl_alt": altitude_meters,
                "yaw": yaw,
                "image_data_binary": Binary(image_bytes[:5000000])  # Store as binary (limit to 5MB)
            },
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            }
        }

    except Exception as e:
        logging.error(f"Error processing image {filepath}: {e}")
        return None


def extract_gps(tags):
    """Extracts latitude and longitude from EXIF data."""
    try:
        if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
            lat = convert_to_degrees(tags['GPS GPSLatitude'], tags['GPS GPSLatitudeRef'].values)
            lon = convert_to_degrees(tags['GPS GPSLongitude'], tags['GPS GPSLongitudeRef'].values)
            return lat - LATITUDE_OFFSET, lon - LONGITUDE_OFFSET
    except Exception as e:
        logging.warning(f"Error extracting GPS data: {e}")
    return None, None

def extract_yaw(tags):
    """Extracts yaw (direction) from EXIF data."""
    try:
        if 'GPS GPSImgDirection' in tags:
            direction = tags['GPS GPSImgDirection'].values[0]
            return float(direction.num) / float(direction.den)
    except Exception as e:
        logging.warning(f"Error extracting yaw: {e}")
    return "Unknown"

def extract_altitude(tags):
    """Extracts altitude from EXIF data."""
    try:
        if 'GPS GPSAltitude' in tags:
            altitude = tags['GPS GPSAltitude'].values[0]
            return float(altitude.num) / float(altitude.den)
    except Exception as e:
        logging.warning(f"Error extracting altitude: {e}")
    return None

def convert_to_degrees(value, ref):
    """Converts EXIF GPS coordinates to decimal degrees."""
    try:
        d = value.values[0].num / value.values[0].den
        m = value.values[1].num / value.values[1].den
        s = value.values[2].num / value.values[2].den
        result = d + (m / 60.0) + (s / 3600.0)
        return -result if ref in ['S', 'W'] else result
    except Exception as e:
        logging.warning(f"Error converting GPS coordinates: {e}")
        return None

def get_images(test_mode=False):
    """Scans directory, processes images, and inserts a FeatureCollection into MongoDB."""
    client = connect_to_mongodb()
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]

    features = []

    logging.info(f"Scanning directory: {UPLOAD_FOLDERS}")
    for folder, _, filenames in os.walk(UPLOAD_FOLDERS):
        for filename in filenames:
            if allowed_file(filename):
                filepath = os.path.join(folder, filename)
                image_metadata = process_image(filepath)
                if image_metadata:
                    # Insert feature without an "id" (MongoDB will generate `_id`)
                    result = collection.insert_one(image_metadata)
                    mongo_id = str(result.inserted_id)  # Convert ObjectId to string

                    # Update the document in MongoDB to include an "id" field
                    collection.update_one({"_id": result.inserted_id}, {"$set": {"id": mongo_id}})

                    # Update the local feature object before appending
                    image_metadata["id"] = mongo_id
                    features.append(image_metadata)

    # Insert as a single FeatureCollection document
    if features:
        geojson_data = {
            "type": "FeatureCollection",
            "features": features
        }
        collection.insert_one(geojson_data)
        logging.info(f"Inserted FeatureCollection with {len(features)} features.")

    client.close()



if __name__ == "__main__":
    logging.info("Starting image processing...")

    test_mode = False
    get_images(test_mode)

    logging.info("Image processing completed.")
