import os
import exifread
import logging
from flask import Blueprint, render_template, jsonify, request, redirect, url_for
from werkzeug.utils import secure_filename

bp = Blueprint('main', __name__)

# Set up logging
# logging.basicConfig(level=logging.DEBUG)  # Uncomment to see metadata values in the console

# Ensure the 'uploads' directories exist
UPLOAD_FOLDERS = [
   ## going to be database connection
]
for folder in UPLOAD_FOLDERS:
    os.makedirs(folder, exist_ok=True)

ALLOWED_EXTENSIONS = {'jpg', 'jpeg'}

# Differential offset values
LATITUDE_OFFSET = 0.00004
LONGITUDE_OFFSET = 0.00
AGL_OFFSET_FEET = -10  # Adjust to make AGL values around 20 feet

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/')
def index():
    return render_template('index.html', mapbox_token=os.getenv('MAPBOX_TOKEN'))

@bp.route('/images')
def get_images():
    images = []

    for root_folder in UPLOAD_FOLDERS:
        for folder, _, filenames in os.walk(root_folder):
            for filename in filenames:
                if filename.lower().endswith('.jpg'):
                    filepath = os.path.join(folder, filename)
                    with open(filepath, 'rb') as f:
                        tags = exifread.process_file(f)

                        gps_latitude = tags.get('GPS GPSLatitude')
                        gps_longitude = tags.get('GPS GPSLongitude')
                        gps_latitude_ref = tags.get('GPS GPSLatitudeRef')
                        gps_longitude_ref = tags.get('GPS GPSLongitudeRef')
                        gps_altitude = tags.get('GPS GPSAltitude')
                        gps_img_direction = tags.get('GPS GPSImgDirection')

                        if gps_latitude and gps_longitude and gps_latitude_ref and gps_longitude_ref:
                            lat = convert_to_degrees(gps_latitude, gps_latitude_ref.values)
                            lon = convert_to_degrees(gps_longitude, gps_longitude_ref.values)
                            yaw = float(gps_img_direction.values[0].num) / float(gps_img_direction.values[0].den) if gps_img_direction else 'Unknown'

                            # Apply differential offset
                            lat -= LATITUDE_OFFSET
                            lon -= LONGITUDE_OFFSET

                            # Parse altitude correctly
                            if gps_altitude:
                                altitude_meters = float(gps_altitude.values[0].num) / float(gps_altitude.values[0].den)
                            else:
                                altitude_meters = None

                            # Without Google Maps, we won't have ground elevation data
                            agl = 'undefined'
                            agl_feet = 'undefined'

                            logging.debug(f"Image: {filename}, Latitude: {lat}, Longitude: {lon}, Yaw: {yaw}, MSL Altitude: {altitude_meters} meters, AGL: {agl} meters, AGL: {agl_feet} feet")

                            images.append({
                                'filename': filename,
                                'lat': lat,
                                'lon': lon,
                                'yaw': yaw,
                                'msl_alt': altitude_meters,
                                'agl': agl,
                                'agl_feet': agl_feet
                            })

    return jsonify(images)

def convert_to_degrees(value, ref):
    d = value.values[0].num / value.values[0].den
    m = value.values[1].num / value.values[1].den
    s = value.values[2].num / value.values[2].den
    result = d + (m / 60.0) + (s / 3600.0)
    if ref in ['S', 'W']:
        result = -result
    return result

@bp.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        files = request.files.getlist('file')
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(UPLOAD_FOLDERS[-1], filename))  # Save to the main images folder
        return redirect(url_for('main.index'))
    return render_template('upload.html')

@bp.route('/categorize', methods=['GET', 'POST'])
def categorize_images():
    uncategorized_images = os.listdir(UPLOAD_FOLDERS[-1])  # Main images folder
    uncategorized_images = [img for img in uncategorized_images if img.lower().endswith(('.png', '.jpg', '.jpeg'))]
    
    if request.method == 'POST':
        image = request.form.get('image')
        category = request.form.get('category')
        if image and category:
            source = os.path.join(UPLOAD_FOLDERS[-1], image)
            destination_folder = next((folder for folder in UPLOAD_FOLDERS if category in folder), None)
            if destination_folder:
                destination = os.path.join(destination_folder, image)
                os.rename(source, destination)
            return redirect(url_for('main.categorize_images'))
    
    current_image = uncategorized_images[0] if uncategorized_images else None
    
    return render_template('categorize.html', current_image=current_image)
