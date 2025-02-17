venv\Scripts\activate    


docker build -t flask_app . 


run -p 5000:5000 flask_app  

python3 -m venv myenv
source myenv/bin/activate
pip3 install -r requirements.txt

 docker-compose up --build