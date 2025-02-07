from pymongo import MongoClient
from bson import Binary  # <-- for storing raw bytes in MongoDB
import os
import exifread
import logging

# MongoDB connection details
MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "seniorDesignTesting"
COLLECTION_NAME = "sendAndRecievePlantInfoTest"

# Define the upload folder
UPLOAD_FOLDERS = r"C:\Users\frost\OneDrive - The Pennsylvania State University\DRONES ONLY\2024_drone_images\purple_loosestrife\07-17-2024"

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDERS, exist_ok=True)

# Offsets
LATITUDE_OFFSET = 0.00004
LONGITUDE_OFFSET = 0.00
AGL_OFFSET_FEET = -10
ALLOWED_EXTENSIONS = {'JPG', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def connect_to_mongodb():
    try:
        client = MongoClient(MONGO_URI)
        client.admin.command("ping")
        print("Connected successfully to MongoDB")
        return client
    except Exception as e:
        raise Exception("The following error occurred while connecting to MongoDB: ", e)

def insert_image_metadata(collection, metadata):
    try:
        result = collection.insert_one(metadata)
        print(f"Inserted document with id: {result.inserted_id}")
    except Exception as e:
        raise Exception("The following error occurred while inserting metadata: ", e)

def get_images():
    client = connect_to_mongodb()
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]
    
    images = []
    image_count = 0
    max_images_to_process = 5

    for folder, _, filenames in os.walk(UPLOAD_FOLDERS):
        for filename in filenames:
            if image_count >= max_images_to_process:
                break

            if filename.lower().endswith('.jpg'):
                filepath = os.path.join(folder, filename)
                
                with open(filepath, 'rb') as f:
                    tags = exifread.process_file(f)
                    image_bytes = f.read()  # Read binary in the same pass

                if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
                    lat = convert_to_degrees(tags['GPS GPSLatitude'], tags['GPS GPSLatitudeRef'].values)
                    lon = convert_to_degrees(tags['GPS GPSLongitude'], tags['GPS GPSLongitudeRef'].values)
                    lat -= LATITUDE_OFFSET
                    lon -= LONGITUDE_OFFSET
                else:
                    lat, lon = None, None  # Handle missing GPS data
                
                yaw = (
                    float(tags['GPS GPSImgDirection'].values[0].num) / 
                    float(tags['GPS GPSImgDirection'].values[0].den)
                    if 'GPS GPSImgDirection' in tags else 'Unknown'
                )

                altitude_meters = (
                    float(tags['GPS GPSAltitude'].values[0].num) /
                    float(tags['GPS GPSAltitude'].values[0].den)
                    if 'GPS GPSAltitude' in tags else None
                )

                image_metadata = {
                    'filename': filename,
                    'lat': lat,
                    'lon': lon,
                    'yaw': yaw,
                    'msl_alt': altitude_meters,
                    'agl': 'undefined',
                    'agl_feet': 'undefined',
                    'image_data': Binary(image_bytes)  
                }

                images.append(image_metadata)
                image_count += 1

    if images:
        collection.insert_many(images)  # Insert all at once
        print(f"Inserted {len(images)} images into MongoDB")

    client.close()
    return images


def convert_to_degrees(value, ref):
    d = value.values[0].num / value.values[0].den
    m = value.values[1].num / value.values[1].den
    s = value.values[2].num / value.values[2].den
    result = d + (m / 60.0) + (s / 3600.0)
    if ref in ['S', 'W']:
        result = -result
    return result

if __name__ == "__main__":
    images = get_images()
    print(f"Processed {len(images)} images.")
