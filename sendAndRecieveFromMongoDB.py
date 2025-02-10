from pymongo import MongoClient
from bson import Binary  # <-- for storing raw bytes in MongoDB
import os
import exifread
import logging

import socket

# Use 'mongodbtest' if running inside Docker, otherwise use 'localhost'
MONGO_HOST = "mongodbtest" if socket.gethostname() == "flask_app" else "localhost"
MONGO_URI = f"mongodb://{MONGO_HOST}:27017/"

DATABASE_NAME = "seniorDesignTesting"
COLLECTION_NAME = "sendAndRecievePlantInfoTest"

# Define the upload folder
UPLOAD_FOLDERS = r"C:\Users\frost\OneDrive - The Pennsylvania State University\DRONES ONLY\2024_drone_images\purple_loosestrife"

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDERS, exist_ok=True)

# Offsets
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
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        logging.info(" Connected successfully to MongoDB.")
        return client
    except Exception as e:
        logging.error(f" MongoDB connection failed: {e}")
        raise Exception("Error connecting to MongoDB.") from e

def insert_image_metadata(collection, metadata):
    """Insert a single document into MongoDB."""
    try:
        result = collection.insert_one(metadata)
        logging.info(f" Inserted document with id: {result.inserted_id}")
    except Exception as e:
        logging.error(f" Error inserting metadata: {e}")
        raise Exception("Error inserting metadata.") from e

def process_image(filepath):
    """Extracts metadata and returns a dictionary for MongoDB insertion."""
    try:
        with open(filepath, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            image_bytes = f.read()

        lat, lon = extract_gps(tags)
        yaw = extract_yaw(tags)
        altitude_meters = extract_altitude(tags)

        return {
            'filename': os.path.basename(filepath),
            'lat': lat,
            'lon': lon,
            'yaw': yaw,
            'msl_alt': altitude_meters,
            'agl': 'undefined',
            'agl_feet': 'undefined',
            'image_data': Binary(image_bytes)  # Store raw binary data
        }
    except Exception as e:
        logging.error(f" Error processing image {filepath}: {e}")
        return None

def extract_gps(tags):
    """Extracts latitude and longitude from EXIF data."""
    try:
        if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
            lat = convert_to_degrees(tags['GPS GPSLatitude'], tags['GPS GPSLatitudeRef'].values)
            lon = convert_to_degrees(tags['GPS GPSLongitude'], tags['GPS GPSLongitudeRef'].values)
            return lat - LATITUDE_OFFSET, lon - LONGITUDE_OFFSET
    except Exception as e:
        logging.warning(f" Error extracting GPS data: {e}")
    return None, None

def extract_yaw(tags):
    """Extracts yaw (direction) from EXIF data."""
    try:
        if 'GPS GPSImgDirection' in tags:
            direction = tags['GPS GPSImgDirection'].values[0]
            return float(direction.num) / float(direction.den)
    except Exception as e:
        logging.warning(f" Error extracting yaw: {e}")
    return "Unknown"

def extract_altitude(tags):
    """Extracts altitude from EXIF data."""
    try:
        if 'GPS GPSAltitude' in tags:
            altitude = tags['GPS GPSAltitude'].values[0]
            return float(altitude.num) / float(altitude.den)
    except Exception as e:
        logging.warning(f" Error extracting altitude: {e}")
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
        logging.warning(f" Error converting GPS coordinates: {e}")
        return None

def get_images(test_mode=False):
    """Processes and inserts images into MongoDB (or generates test data)."""
    client = connect_to_mongodb()
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]

    images = []

    if test_mode:
        logging.info(" Running in TEST MODE. Generating mock data.")
        for i in range(5):
            test_metadata = {
                'filename': f'test_image_{i}.jpg',
                'lat': 42.1133 + i * 0.0001,
                'lon': -79.9738 - i * 0.0001,
                'yaw': 10.5 + i,
                'msl_alt': 365.457 + i,
                'agl': 'undefined',
                'agl_feet': 'undefined',
                #'image_data': Binary(b"testbinarydata")
            }
            images.append(test_metadata)
    else:
        logging.info(f"Scanning directory: {UPLOAD_FOLDERS}")

        for folder, _, filenames in os.walk(UPLOAD_FOLDERS):
            for filename in filenames:
                if allowed_file(filename):
                    filepath = os.path.join(folder, filename)
                    image_metadata = process_image(filepath)
                    if image_metadata:
                        images.append(image_metadata)

    if images:
        collection.insert_many(images)
        logging.info(f" Inserted {len(images)} images into MongoDB.")

    client.close()
    return images

if __name__ == "__main__":
    logging.info(" Starting image processing...")
    
    # Toggle test mode to True to generate mock data
    test_mode = False 
    images = get_images(test_mode)

    logging.info(f" Processed {len(images)} images.")