# MediaJam / Mediahillo

MediaJam (Mediahillo) is a long term preservation packaging tool interface, developed in FInnish National Gallery.
MediaJam is a Flask application working in Python 3 environment.

MediaJam uses dpres-siptools commands for packaging files. Therefore dpres-siptools MUST be installed to the same server.
https://github.com/Digital-Preservation-Finland/dpres-siptools

MediaJam can get descriptive metadata from MuseumPlus collection management system through API-interface.
https://museoliitto.fi/kookos/

Application is tested with AlmaLinux 9 server. Flask application was installed as a reverse-proxy installation with Gunicorn and NGINX www-servers.
https://gunicorn.org/

![MediaJam / Mediahillo](/static/FNG-Siptools.jpg | width=400)

## Installation
As user root:
``````
adduser pasisti
passwd pasisti
``````
### Install MediaJam as user pasisti:
``````
cd /home/pasisti
git clone https://github.com/FinnishNationalGallery/mediajam.git mediahillo
cd mediahillo
python3 -m venv venv/ 
source venv/bin/activate
pip install -r requirements.txt
``````
### Install dpres-siptools as user pasisti:
``````
cd /home/pasisti/mediahillo
git clone https://github.com/Digital-Preservation-Finland/dpres-siptools
cd dpres-siptools
pip install --upgrade pip==20.2.4 setuptools
pip install -r requirements_github.txt
pip install .
import-object --help
``````
### Install and configure NGINX as user root:
``````
dnf update -y && dnf upgrade -y
dnf install nano
dnf install nginx -y
systemctl enable nginx
systemctl start nginx
# Configure nginx using gunicorn reverse proxy installation
nano /etc/nginx/nginx.conf
# Add this configuration to nginx.conf file
        location / {
        proxy_read_timeout 28800;
        proxy_connect_timeout 28800;        proxy_send_timeout 28800;
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Prefix /;
        # upstream sent too big header while reading response header from upstream
        proxy_busy_buffers_size   512k;
        proxy_buffers   4 512k;
        proxy_buffer_size   256k;
        }
# 
systemctl restart nginx
``````
### Start Flask application with gunicorn www-server as user pasisti:
``````
cd /home/pasisti/mediahillo
# Configure .env file from env.txt 
nano env.txt
cp env.txt .env
# Start gunicorn www-server as reverse proxy
gunicorn -w 1 --timeout 28800 'app:app'
# Now you can go to servers home page and see MediaJam in action
``````
#### Other commands for gunicorn management:
``````
# Start gunicorn to background and use access and error logfiles
gunicorn -w 1 --timeout 28800 'app:app' --access-logfile gunicorn-access.txt --error-logfile gunicorn-error.txt &
# Check if gunicorn processes are in progress
ps -aux | grep "gunicorn"
# Kill gunicorn processes
kill -9 #process number
``````