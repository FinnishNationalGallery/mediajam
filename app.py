from flask import Flask, render_template, request, url_for, flash, redirect, send_file, session, jsonify
from markupsafe import Markup
import os
import glob
import shutil
import subprocess
import datetime
from dateutil import parser
import uuid
import json
from subprocess import PIPE
from dotenv import dotenv_values
#from flask_executor import Executor
import modules.mp_metadata as mp_metadata
import modules.form_metadata as form_metadata
import modules.pas_sftp as pas_sftp
import modules.pas_rest as pas_rest
import modules.mp_paslog_mod as mp_paslog_mod
from flask_sqlalchemy import SQLAlchemy
##############################
# This is needed when Flask application is behind proxy
from werkzeug.middleware.proxy_fix import ProxyFix
##############################
#### LOGIN MANAGER IMPORTS 
##############################
from flask_mail import Mail, Message
from flask_login import UserMixin, LoginManager, login_required, login_user,logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from modules.form_login import *
import uuid
#import datetime # This is reguired if not imported earlier
##############################

app = Flask(__name__)
# This is needed when Flask application is behind proxy
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)

#executor = Executor(app)
#app.config['EXECUTOR_TYPE'] = 'thread'
#app.config['EXECUTOR_MAX_WORKERS'] = 5
#app.config['EXECUTOR_PROPAGATE_EXCEPTIONS'] = True

config = dotenv_values(".env") 
app.config['SECRET_KEY'] = config['SECRET_KEY']
APP_SERVER_ADDRESS = config['APP_SERVER_ADDRESS']
APP_FOLDER = config['APP_FOLDER']
SIGNATURE = config['SIGNATURE']
DATA_path = config['DATA_FOLDER']
DATANATIVE_path = config['DATANATIVE_FOLDER']
METADATA_path = config['METADATA_FOLDER']
SIP_path = config['SIP_FOLDER']
SIPLOG_path = config['SIPLOG_FOLDER']
DOWNLOAD_path = config['DOWNLOAD_FOLDER']
SERVER_ffmpeg = config['SERVER_FFMPEG']
ORGANIZATION = config['ORGANIZATION']
CONTRACTID = config['CONTRACTID']

def logfile_output(line):
   file = open(SIPLOG_path+"output.txt", "a")
   file.write(line)
   file.close()

def logfile_outerror(line):
   file = open(SIPLOG_path+"outerror.txt", "a")
   file.write(line)
   file.close()

def logfile_datanative(line):
   file = open(SIPLOG_path+"datanative.txt", "a")
   file.write(line)
   file.close()

def subprocess_args(*args):
   listToStrCmd = '\' \''.join(map(str, list(args)))
   commandStr = '\'' + listToStrCmd + '\''
   # cmd = 'source /home/pasisti/dpres-siptools/venv/bin/activate; ' + commandStr
   cmd = commandStr # No need to activate venv
   out = subprocess.run(cmd, shell=True, executable='/bin/bash',stdout=PIPE, stderr=PIPE, universal_newlines=True)
   logfile_output(commandStr+"\n")
   logfile_output(out.stdout+"\n")
   logfile_outerror(out.stderr)

def get_diskinfo():
   cmd = 'df -h ' + APP_FOLDER
   out = subprocess.run(cmd, shell=True, executable='/bin/bash',stdout=PIPE, stderr=PIPE, universal_newlines=True)
   dioutput = out.stdout
   dioutput = dioutput.split("/dev/")
   diskinfo = dioutput[1]
   diskinfo = diskinfo.split()
   return diskinfo  

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pas_db.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


##############################
#### LOGIN MANAGER 
##############################
app.config['MAIL_SERVER']= config['MAIL_SERVER']
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = config['MAIL_USERNAME']
app.config['MAIL_PASSWORD'] = config['MAIL_PASSWORD']
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
mail = Mail(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
   id = db.Column(db.Integer, primary_key=True)
   username = db.Column(db.String(50), index=True, unique=True)
   email = db.Column(db.String(150), unique = True, index = True)
   password_hash = db.Column(db.String(150))
   joined_at = db.Column(db.DateTime(), default = datetime.datetime.utcnow, index = True)
   token = db.Column(db.String(50))
   def set_token(self, mytoken):
      self.token = mytoken
   def set_password(self, password):
      self.password_hash = generate_password_hash(password)
   def check_password(self,password):
      return check_password_hash(self.password_hash,password)

class db_paslog_mp(db.Model): # This is extra table - does not belong to Login manager
   __tablename__ = 'db_paslog_mp'
   id = db.Column('paslog_id', db.Integer, primary_key = True)
   mp_id = db.Column(db.String(50))
   mp_name = db.Column(db.String(500))
   mp_paslog = db.Column(db.String(500))
   #pas_id = db.Column(db.String(50))  
   #pas_created = db.Column(db.String(50))  
   #pas_log = db.Column(db.String(500))

class db_paslog_csc(db.Model): # This is extra table - does not belong to Login manager
   __tablename__ = 'db_paslog_csc'
   id = db.Column('paslog_id', db.Integer, primary_key = True)
   pas_mp_id = db.Column(db.String(50))
   pas_id = db.Column(db.String(500))  
   pas_created = db.Column(db.String(50))  
   pas_location = db.Column(db.String(500))
   mp_paslog = db.Column(db.String(500))

# This must be done after db.Model classes!
with app.app_context(): # https://flask-sqlalchemy.palletsprojects.com/en/3.0.x/
   db.create_all() # Create_all does not update tables if they are already in the database.

@login_manager.user_loader
def load_user(user_id):
   return User.query.get(user_id)

@app.route('/register/', methods = ['POST','GET'])
def register():
   form = RegistrationForm()
   if form.validate_on_submit():
      try:
         user = User(username =form.username.data, email = form.email.data)
         user.set_password(form.password1.data)
         db.session.add(user)
         db.session.commit()
         return redirect(url_for('login'))
      except Exception as e:
         flash("Error! "+ str(e))
   return render_template('login_registration.html', form=form)

@app.route('/login/', methods=['GET', 'POST'])
def login():
   form = LoginForm()
   if form.validate_on_submit():
      user = User.query.filter_by(email = form.email.data).first()
      if user is not None and user.check_password(form.password.data):
         if form.remember:
            login_user(user, remember=True)
         else:
            login_user(user)
         next = request.args.get("next")
         return redirect(next or url_for('index'))
      flash('Invalid email address or Password.')    
   return render_template('login.html', form=form)

@app.route("/logout/")
# @login_required
def logout():
   logout_user()
   return redirect(url_for('index'))

@app.route('/login_reset_email/', methods = ['POST', 'GET'])
def login_reset_email():
   form = LoginFormReset()
   if form.validate_on_submit():
      try:
         user = User.query.filter_by(email = form.email.data).first()
         mytoken = str(uuid.uuid4())
         user.set_token(mytoken)
         db.session.commit()
         msg = Message('PAS palvelimen käyttäjätunnuksen sähköpostiviesti!', sender = config['MAIL_USERNAME'], recipients = [form.email.data])
         msg.body = "Hei,\n\nOlet pyytänyt salasanan resetointia PAS-paketoinnin palvelussa!\n\nVaihda tunnuksen salasana tästä linkistä: \n\n" + APP_SERVER_ADDRESS + url_for('register_reset', token=mytoken) +"\n\n"
         mail.send(msg)
         flash("Email send to : "+form.email.data)
      except Exception as e:
         flash("Error! " + str(e))
   return render_template("login_reset_email.html", form=form)

@app.route('/register_reset/<string:token>', methods = ['POST','GET'])
def register_reset(token):
   form = RegistrationFormReset()
   if form.validate_on_submit():
      try:
         user=User.query.filter_by(token=token).first()
         user.set_password(form.password1.data)
         mytoken = str(uuid.uuid4())
         user.set_token(mytoken)
         db.session.commit()
         flash("Password changed, you can login now!")
         
         return redirect(url_for('login'))
      except Exception as e:
         flash("Error! User with given token not found!")
   try:
      user=User.query.filter_by(token=token).first()
      flash(user.email)
   except:
      flash("Reset link has expired!")
   return render_template('login_registration_reset.html', form=form, token=token)

####################################
### ROUTES
####################################
@app.route("/")
def index():
   return render_template('index.html')

####################################
### FFMPEG
####################################
@app.route("/ffmpeg")
def ffmpeg():
   return render_template('ffmpeg_info.html')

####################################
### SETTINGS
####################################
@app.route("/settings", methods=['GET', 'POST'])
@login_required
def settings():
   form = form_metadata.Settings()
   if form.validate_on_submit():
      normalization_date = form.premis_video_normalization_date.data
      normalization_date_str = normalization_date.strftime('%Y-%m-%dT%H:%M')
      normalization_agent = form.premis_video_normalization_agent.data
      mets_createdate = form.mets_createdate.data
      settings = {
        "prem_norm_date": normalization_date_str,
        "prem_norm_agent": normalization_agent,
        "mets_createdate": mets_createdate}
      json_obj = json.dumps(settings, indent=4)
      try:
         file = open("settings.json", "w")
         file.write(json_obj)
         file.close()
         message = Markup("Settings saved succesfully!")
         flash(message, 'success')
      except:
         message = Markup("Error saving settings file!")
         flash(message, 'error')
   else:
      try:
         file = open("settings.json", "r")
         content = file.read()
         settings = json.loads(content)
         file.close()
      except:
         settings = {
         "prem_norm_date": "",
         "prem_norm_agent": "",
         "mets_createdate": ""}
         json_obj = json.dumps(settings, indent=4)
         file = open("settings.json", "w")
         file.write(json_obj)
         file.close()
   return render_template('settings.html', form=form, settings=settings)

####################################
### DATA 
####################################
@app.route('/data')
@login_required
def data():
   files = sorted(os.listdir(DATA_path))
   diskinfo = get_diskinfo()
   if 'message' in session:
      pass
   else:
      session['message'] = ""
   return render_template('data.html', files=files, diskinfo=diskinfo)

@app.route('/data_import_all')
@login_required
def data_import_all():
   data_import_skip()
   mix_create()
   videomd_create()
   audiomd_create()
   #data_premis_event_ffmpeg_ffv1()
   #data_premis_event_frame_md()
   return redirect(url_for('sip'))

@app.route('/data_import_skip')
@login_required
def data_import_skip():
   redir = request.args.get('flag')
   subprocess_args('import-object', '--workspace', SIP_path, '--skip_wellformed_check', DATA_path)
   #executor.submit_stored('IMPORT', subprocess_args, 'import-object', '--workspace', SIP_path, '--skip_wellformed_check', DATA_path)
   if redir == 'once':
      return redirect(url_for('sip'))
   return True

@app.route('/mix_create')
@login_required
def mix_create():
   redir = request.args.get('flag') # If you want to make own button for this function
   files = os.listdir(DATA_path)
   for file in files:
      filesplit = file.split('.')
      extension = filesplit[-1].lower()
      filepath = DATA_path + file
      if extension in ['jpg', 'jpeg', 'png', 'tif', 'tiff']:
         subprocess_args('create-mix','--workspace', SIP_path, filepath)
         #executor.submit_stored('MIX', subprocess_args, 'create-mix','--workspace', SIP_path, filepath)
   if redir == 'once':
      return redirect(url_for('sip'))
   return True

@app.route('/videomd_create')
@login_required
def videomd_create():
   redir = request.args.get('flag') # If you want to make own button for this function
   files = os.listdir(DATA_path)
   for file in files:
      filesplit = file.split('.')
      extension = filesplit[-1].lower()
      filepath = DATA_path + file
      if extension in ['mp4', 'mpg', 'mpeg', 'mov', 'mkv', 'avi']:
         subprocess_args('create-videomd', '--workspace', SIP_path, filepath)
         #executor.submit_stored('VIDEOMD', subprocess_args, 'create-videomd', '--workspace', SIP_path, filepath)
   if redir == 'once':
      return redirect(url_for('sip'))
   return True

@app.route('/audiomd_create')
@login_required
def audiomd_create():
   redir = request.args.get('flag') # If you want to make own button for this function
   files = os.listdir(DATA_path)
   for file in files:
      filesplit = file.split('.')
      extension = filesplit[-1].lower()
      filepath = DATA_path + file
      if extension in ['mp4', 'mpg', 'mpeg', 'mov', 'mkv', 'avi']:
         subprocess_args('create-audiomd','--workspace', SIP_path, filepath)
         #executor.submit_stored('AUDIOMD', subprocess_args, 'create-audiomd','--workspace', SIP_path, filepath)
   if redir == 'once':
      return redirect(url_for('sip'))
   return True

@app.route('/addml_create')
@login_required
def addml_create():
   redir = request.args.get('flag') # If you want to make own button for this function
   files = os.listdir(DATA_path)
   for file in files:
      filesplit = file.split('.')
      extension = filesplit[-1].lower()
      filepath = DATA_path + file
      if extension in ['csv']:
         subprocess_args('create-addml',filepath, '--workspace', SIP_path, ' --header', '--charset', 'UTF8', '--sep', 'CR+LF', '--quot', '"', '--delim' ',')
   if redir == 'once':
      return redirect(url_for('sip'))
   return True

@app.route('/data_premis_event_ffmpeg_ffv1')
@login_required
def data_premis_event_ffmpeg_ffv1(): # Matroska video FFMPEG normalization event
   redir = request.args.get('flag') # If you want to make own button for this function
   files = os.listdir(DATA_path)
   ###
   file = open("settings.json", "r")
   content = file.read()
   settings = json.loads(content)
   file.close()
   event_time = settings['prem_norm_date']
   agent_name = settings['prem_norm_agent']
   ###
   for file in files:
      filesplit = file.split('.')
      extension = filesplit[-1].lower()
      filepath = DATA_path + file
      if extension in ['mkv']: # Only for Matroska .mkv files!
         event_type = "normalization"
         #event_time = datetime.datetime.now()
         event_detail = "File conversion with FFMPEG program"
         event_outcome = "success"
         event_outcome_detail = "FFV1 video in Matroska container"
         #agent_name = "FFMPEG version git-2020-01-26-5e62100 / Windows 10"
         agent_type = "software"
         datetime_obj = parser.parse(event_time)
         CreateDate = datetime_obj.isoformat()
         subprocess_args('premis-event', event_type, CreateDate, '--event_detail', event_detail, '--event_outcome', event_outcome, '--event_outcome_detail', event_outcome_detail, '--workspace', SIP_path, '--agent_name', agent_name, '--agent_type', agent_type, '--event_target', filepath.replace("./",""))
   if redir == 'once':
      return redirect(url_for('sip'))
   return True

@app.route('/data_premis_event_frame_md') # Calculate video frame checksum
@login_required
def data_premis_event_frame_md():
   redir = request.args.get('flag') # If you want to make own button for this function
   files = os.listdir(DATA_path)
   for file in files:
      filesplit = file.split('.')
      extension = filesplit[-1].lower()
      filepath = DATA_path + file
      if extension in ['mkv']: # Only for Matroska .mkv files!
         try: # Get MD5 video frame checksum from file
            cmd = 'ffmpeg -loglevel error -i ' + filepath + ' -map 0:v -f md5 -'
            out = subprocess.run(cmd, shell=True, executable='/bin/bash',stdout=PIPE, stderr=PIPE, universal_newlines=True)
            logfile_output(cmd+"\n")
            logfile_output(out.stdout+"\n")
            logfile_outerror(out.stderr)
            session['message_md5'] = out.stdout
         except:
            logfile_outerror(out.stderr)
         # Create Premis-event for frame checksum
         CreateDate = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).isoformat() # "2018-04-12T14:09:00.233"
         subprocess_args('premis-event', 'message digest calculation', CreateDate, '--event_detail', 'ffmpeg -loglevel error -i ' + file + ' -map 0:v -f md5 -', '--event_outcome', 'success', '--event_outcome_detail', session['message_md5'], '--workspace', SIP_path, '--agent_name', SERVER_ffmpeg, '--agent_type', 'software', '--event_target', filepath.replace("./",""))
   if redir == 'once':
      return redirect(url_for('sip'))
   return True

@app.route("/data_delete")
@login_required
def data_delete():
   delete_really = request.args.get('delete') 
   if delete_really == "True":
      try:
         shutil.rmtree(DATA_path)
         os.mkdir(DATA_path)
         session['mp_inv'] = ""
         session['mp_id'] = ""
         session['mp_name'] = ""
         session['mp_created'] = ""
      except:
         message = "Could not delete folder!"
         flash(message, 'error')
   else:
      message = Markup("Do you really want to delete this folder? <a href=" + url_for('data_delete', delete="True") + "><button class=\"button is-danger\">Delete</button></a> "+" <a href=" + url_for('data') + "><button class=\"button is-dark\">Cancel</button> </a>")
      flash(message, 'error')
   return redirect(url_for('data'))

####################################
### DATANATIVE
####################################
@app.route('/datanative')
@login_required
def datanative():
   files = sorted(os.listdir(DATANATIVE_path))
   files_outcome = sorted(os.listdir(DATA_path))
   diskinfo = get_diskinfo()
   try:
      with open(SIPLOG_path+"datanative.txt") as f:
         datanative = f.read()
   except:
      datanative = ""
   if 'message' in session:
      pass
   else:
      session['message'] = ""
   return render_template('datanative.html', files=files, files_outcome=files_outcome, diskinfo=diskinfo, datanative=datanative)

@app.route('/datanative_import/', methods=['GET', 'POST'])
@login_required
def datanative_import():
   diskinfo = get_diskinfo()
   file = open("settings.json", "r")
   content = file.read()
   settings = json.loads(content)
   file.close()
   event_time = settings['prem_norm_date']
   agent_name = settings['prem_norm_agent']
   try:
      with open(SIPLOG_path+"datanative.txt") as f:
         datanative = f.read()
   except:
      datanative = ""
   if request.method == 'POST':
      file = request.form['file']
      outcome = request.form['outcome']
      datetime_obj = parser.parse(event_time)
      CreateDate = datetime_obj.isoformat()
      subprocess_args('import-object', '--workspace', SIP_path, '--skip_wellformed_check', DATANATIVE_path + file)
      subprocess_args('premis-event', 'normalization', CreateDate, '--workspace', SIP_path, '--event_detail', 'File conversion with FFMPEG program', '--event_outcome', 'success', '--event_outcome_detail', 'FFV1 video in Matroska container', '--agent_name', agent_name, '--agent_type', 'software', '--linking_object', 'source', DATANATIVE_path + file, '--linking_object', 'outcome', DATA_path + outcome, '--add_object_links')
      #
      logfile_datanative("Original file: "+file+" >>> "+"Normalized file: "+outcome+"\n")   

   #return redirect(url_for('datanative'))
   return render_template('datanative_import.html', file=file, outcome=outcome, diskinfo=diskinfo, datanative=datanative)

####################################
### METADATA
####################################
@app.route("/metadata")
@login_required
def metadata():
   files = sorted(os.listdir(METADATA_path))
   return render_template('metadata.html', files=files, environment=mp_metadata.MP_ENV)

@app.route("/metadata_get")
@login_required
def metadata_get():
   return render_template('index.html')

@app.route("/metadata_save_object_by_id")
@login_required
def metadata_save_object_by_id():
   objectid = request.args.get('objectid')
   #object_id = request.vars.object_id
   message = mp_metadata.save_object_by_id(objectid)
   if len(message) > 1:
          flash("Something went wrong when saving object XML file. ERROR MESSAGE: " + message, 'error')
   return redirect(url_for('data'))

@app.route("/metadata_create_lido_xml")
@login_required
def metadata_create_lido_xml():
   objectid = request.args.get('objectid')
   session['mp_inv'] = ""
   session['mp_id'] = ""
   session['mp_name'] = ""
   #object_id = request.vars.object_id
   message = mp_metadata.create_lido_xml(objectid)
   if len(message) > 1:
          flash("Something went wrong when creating Lido XML file. ERROR MESSAGE: " + message, 'error')
   return redirect(url_for('metadata'))

@app.route("/metadata_load_attachment")
@login_required
def metadata_load_attachment():
   objectid = request.args.get('objectid')
   objectname = request.args.get('objectname')
   object_id = request.args.get('img_id')
   object_name = request.args.get('img_name')
   try:
      input = mp_metadata.load_attachment(object_id)
      with open(DATA_path+object_name,'wb') as f:
         shutil.copyfileobj(input, f)
      message = Markup("<a href="+url_for('metadata_object_by_id', objectid=objectid)+"> Go back to previous MuseumPlus Object!</a>")
      flash(message, 'success')
   except:
      flash("Something went wrong when downloading attachment file!", 'error' )
   return redirect(url_for('data'))

@app.route("/metadata_read_lido_xml")
@login_required
def metadata_read_lido_xml():
   mp_inv, mp_id, mp_name, mp_created = mp_metadata.read_lido_xml()
   session['mp_inv'] = mp_inv
   session['mp_id'] = mp_id
   session['mp_name'] = mp_name
   session['mp_created'] = mp_created
   files = os.listdir(METADATA_path)
   return render_template('metadata.html', files=files)
   #return render_template('metadata_read_lido.html', mp_inv=mp_inv, mp_id=mp_id, mp_created=mp_created)

@app.route('/metadata_import_description')
@login_required
def metadata_import_description():
   subprocess_args('import-description', METADATA_path+'lido_description.xml', '--workspace', SIP_path)
   return redirect(url_for('sip'))


@app.route('/metadata_search/', methods=['GET', 'POST'])
@login_required
def metadata_search():
   form = form_metadata.SearchMuseumPlus()
   if form.validate_on_submit():
      objectid = form.objectid.data
      invnumber = form.inventorynumber.data
      title = form.title.data
      message = objectid + invnumber + title
      if len(objectid) > 3:
         return redirect(url_for('metadata_object_by_id', objectid=objectid))
      elif len(invnumber) > 3:
         return redirect(url_for('get_object_by_inv', invnumber=invnumber))
      elif len(title) > 3:
         return redirect(url_for('get_object_by_title', title=title))
      else:
         flash('Minimum length for search field is 3 characters!', 'error')
         return render_template('metadata_search.html', form=form, message=message)
   message = ""
   return render_template('metadata_search.html', form=form, message=message, environment=mp_metadata.MP_ENV)

@app.route('/metadata_object_by_id/', methods=['GET', 'POST'])
@login_required
def metadata_object_by_id():
   back = request.referrer
   objectid = request.args.get('objectid')
   xml_data, thumb_status = mp_metadata.get_object_by_id(objectid)
   return render_template('metadata_object_by_id.html', xml_data=xml_data, thumb_status=thumb_status, objectid=objectid, back=back)

@app.route('/get_object_by_inv/', methods=['GET', 'POST'])
@login_required
def get_object_by_inv():
   back = request.referrer
   invnumber = request.args.get('invnumber')
   totalSize, mylist, xml = mp_metadata.get_object_by_number(invnumber)
   return render_template('metadata_object_by_inv.html', totalSize=totalSize, objects=mylist, xml=xml, back=back)

@app.route('/get_object_by_title/', methods=['GET', 'POST'])
@login_required
def get_object_by_title():
   back = request.referrer
   title = request.args.get('title')
   totalSize, mylist, xml = mp_metadata.get_object_by_title(title)
   return render_template('metadata_object_by_title.html', title=title, totalSize=totalSize, objects=mylist, xml=xml, back=back)

@app.route("/metadata_delete")
@login_required
def metadata_delete():
   delete_really = request.args.get('delete') 
   if delete_really == "True":
      try:
         shutil.rmtree(METADATA_path)
         os.mkdir(METADATA_path)
         session['mp_inv'] = ""
         session['mp_id'] = ""
         session['mp_name'] = ""
         session['mp_created'] = ""
      except:
         message = "Could not delete folder!"
         flash(message, 'error')
   else:
      message = Markup("Do you really want to delete this folder? <a href=" + url_for('metadata_delete', delete="True") + "><button class=\"button is-danger\">Delete</button></a>"+" <a href=" + url_for('metadata') + "><button class=\"button is-dark\">Cancel</button> </a>")
      flash(message, 'error')
   return redirect(url_for('metadata'))

###################################
### SIP 
###################################
@app.route("/sip")
@login_required
def sip():
   diskinfo = get_diskinfo()
   try:
      with open(SIPLOG_path+"output.txt") as f:
         output = f.read()
   except:
      output = ""
   try:   
      with open(SIPLOG_path+"outerror.txt") as f:
         outerr = f.read()
   except:
      outerr = ""
   files = sorted(os.listdir(SIP_path))
   ###
   return render_template('sip.html', files=files, diskinfo=diskinfo, output=output, outerr=outerr)

@app.route("/sip_make_all")
@login_required
def sip_make_all():
   sip_premis_event_created()
   sip_compile_structmap()
   sip_compile_mets()
   sip_sign_mets()
   return redirect(url_for('sip'))

@app.route("/sip_premis_event_created") # MuseumPlus digital object creation
@login_required
def sip_premis_event_created():
   redir = request.args.get('flag') # If you want to make own button for this function
   event_type = "creation"
   event_detail = "MuseumPlus object creation"
   event_outcome = "success"
   event_outcome_detail = "MuseumPlus object creation premis-event succeeded"
   agent_name = "MuseumPlus"
   agent_type = "software"
   if not session['mp_created']: # Try get date from MuseumPlus Lido read
      session['mp_created'] = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).isoformat()
      #session['mp_created'] = "2018-04-12T14:09:00.233"
   subprocess_args('premis-event', event_type, session['mp_created'], '--event_detail', event_detail, '--event_outcome', event_outcome, '--event_outcome_detail', event_outcome_detail, '--workspace', SIP_path, '--agent_name', agent_name, '--agent_type', agent_type)
   if redir == 'once':
      return redirect(url_for('sip'))
   return True

@app.route("/sip_compile_structmap")
@login_required
def sip_compile_structmap():
   redir = request.args.get('flag') # If you want to make own button for this function
   subprocess_args('compile-structmap', '--workspace', SIP_path)
   if redir == 'once':
      return redirect(url_for('sip'))
   return True

@app.route("/sip_compile_mets")
@login_required
def sip_compile_mets():
   redir = request.args.get('flag') # If you want to make own button for this function
   if session['mp_inv']:
      objid = session['mp_inv']
   else:
      objid = str(uuid.uuid1())
   subprocess_args('compile-mets','--workspace', SIP_path , 'ch', ORGANIZATION, CONTRACTID, '--objid',objid, '--copy_files', '--clean')
   if redir == 'once':
      return redirect(url_for('sip'))
   return True

@app.route("/sip_compile_mets_update")
@login_required
def sip_compile_mets_update():
   redir = request.args.get('flag') # If you want to make own button for this function
   LastmodDate = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).isoformat() 
   ###
   file = open("settings.json", "r")
   content = file.read()
   settings = json.loads(content)
   file.close()
   mets_createdate = settings['mets_createdate']
   ###
   if session['mp_inv']:
      objid = session['mp_inv']
   else:
      objid = str(uuid.uuid1())
   subprocess_args('compile-mets','--workspace', SIP_path , 'ch', ORGANIZATION, CONTRACTID, '--objid',objid, '--create_date', mets_createdate, '--last_moddate', LastmodDate, '--record_status', 'update', '--copy_files', '--clean')
   if redir == 'once':
      return redirect(url_for('sip'))
   return True

@app.route("/sip_sign_mets")
@login_required
def sip_sign_mets():
   redir = request.args.get('flag') # If you want to make own button for this function
   #subprocess_args('./sign.sh', '/home/pasisti/mediahillo/signature/sip_sign_pas.pem', SIP_path)
   subprocess_args('./sign.sh', SIGNATURE, SIP_path)
   #subprocess_args('sign-mets', '--workspace', SIP_path, '/home/pasisti/mediahillo/signature/sip_sign_pas.pem')
   if redir == 'once':
      return redirect(url_for('sip'))
   return True

@app.route("/sip_make_tar")
@login_required
def sip_make_tar():
   redir = request.args.get('flag') # If you want to make own button for this function
   lido_inv, lido_id, lido_name, lido_created = mp_metadata.read_mets_lido_xml()
   if lido_id > "":
      sip_filename = lido_id + '.tar'
      message = "TAR package from mets.xml file: "+lido_name + ", Inv nro: " +lido_inv + ", MuseumPlus ID: " + lido_id
      msg_status = "success"
   else:
      sip_filename = str(uuid.uuid1()) + '.tar'
      message = "SOMETHING WENT WRONG! TAR package name is: " + sip_filename
      msg_status = "error"
   subprocess_args('compress', '--tar_filename',  sip_filename, SIP_path)
   if redir == 'once':
      flash( message,msg_status)
      return redirect(url_for('sip'))
   return True

@app.route("/sip_delete")
@login_required
def sip_delete():
   delete_really = request.args.get('delete') 
   if delete_really == "True":
      try:
         os.remove(SIPLOG_path+"output.txt")
         os.remove(SIPLOG_path+"outerror.txt")
         try:
            os.remove(SIPLOG_path+"datanative.txt")
         except:
            pass
         shutil.rmtree(SIP_path)
         os.mkdir(SIP_path)
         session['mp_inv'] = ""
         session['mp_id'] = ""
         session['mp_name'] = ""
         session['mp_created'] = ""
      except:
         message = "Could not delete folder!"
         flash(message, 'error')
   else:
      message = Markup("Do you really want to delete this folder? <a href=" + url_for('sip_delete', delete="True") + "><button class=\"button is-danger\">Delete</button></a>"+" <a href=" + url_for('sip') + "><button class=\"button is-dark\">Cancel</button> </a>")
      flash(message, 'error')
   return redirect(url_for('sip'))

####################################
### DOWNLOAD
####################################
@app.route("/download")
@login_required
def download():
   #files = sorted(os.listdir(DOWNLOAD_path))
   files = list(filter(os.path.isfile, glob.glob(DOWNLOAD_path + "*")))
   files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
   idx = 0
   for item in files:
      if DOWNLOAD_path in item:
         item2 = item.replace(DOWNLOAD_path, "")
         files[idx] = item2
      idx = idx + 1
   return render_template('download.html', files=files)

@app.route("/download_delete")
@login_required
def download_delete():
   delete_really = request.args.get('delete') 
   if delete_really == "True":
      try:
         shutil.rmtree(DOWNLOAD_path)
         os.mkdir(DOWNLOAD_path)
      except:
         message = "Could not delete folder!"
         flash(message, 'error')
   else:
      message = Markup("Do you really want to delete this folder? <a href=" + url_for('download_delete', delete="True") + "><button class=\"button is-danger\">Delete</button></a>"+" <a href=" + url_for('download') + "><button class=\"button is-dark\">Cancel</button> </a>")
      flash(message, 'error')
   return redirect(url_for('download'))

###################################
### DELETE FILE OR FOLDER
###################################
@app.route("/file_delete")
@login_required
def file_delete():
   path = request.args.get('path')
   file = request.args.get('name')
   view = request.args.get('page')
   if path == "DATA":
      path = DATA_path
   elif path == "DATANATIVE":
      path = DATANATIVE_path
   elif path == "METADATA":
      path = METADATA_path
   elif path == "SIP":
      path = SIP_path
   elif path == "DOWNLOAD":
      path = DOWNLOAD_path
   else: 
      path = DATA_path # This is dummy but secure
   deleteMessage = ""
   if os.path.isfile(path + file):
      try:
         os.remove(path + file)
      except:
         deleteMessage = "Cannot delete file!"
   elif os.path.isdir(path + file):
      try:
         shutil.rmtree(path + file)
      except:
         deleteMessage = "Cannot delete directory!"
   return redirect(url_for(view))

###################################
### PAS SFTP
###################################
@app.route("/pas_sftp_index")
@login_required
def pas_sftp_index():
   return render_template('pas_sftp_index.html', environment=pas_sftp.SFTP_ENV)

@app.route("/pas_sftp_folder")
@login_required
def pas_sftp_folder():
   folder = request.args.get('folder')
   data, directories, files = pas_sftp.folder(folder)
   return render_template('pas_sftp_folder.html', folder=folder, data=data, directories=directories, files=files, environment=pas_sftp.SFTP_ENV)

@app.route("/pas_sftp_file")
@login_required
def pas_sftp_file():
   folder = request.args.get('folder')
   file  = request.args.get('file')
   message = pas_sftp.file(folder, file)
   return render_template('pas_sftp_file.html', folder=folder, file=file, message=message, environment=pas_sftp.SFTP_ENV)

###################################
### PAS REST
###################################
@app.route("/pas_rest_index")
@login_required
def pas_rest_index():
   message = "Choose function from left panel"
   return render_template('pas_rest_index.html', environment=pas_rest.REST_ENV, message=message)

@app.route("/pas_rest_status")
@login_required
def pas_rest_status():
   message = pas_rest.get_status()
   return render_template('pas_rest_status.html', environment=pas_rest.REST_ENV, message=message)

@app.route("/pas_rest_accepted_created", methods=['GET', 'POST'])
@login_required
def pas_rest_accepted_created():
   message = ""
   counter = 0
   error = ""
   value = ""
   created = ""
   if request.method == 'POST':
      created = "\"" + request.form['created'] + "\""
      if request.form['created'] == "":
         created = "*"
      if request.form['created'] == "*":
         created = "*"
      value = request.form['created']
      try:
         message, counter, error = pas_rest.get_accepted_created(created)
      except:
         message = {'status': 'fail', 'data': {'message': 'Error with REST command!'}}
         counter = ""
         error = ""
         value = ""
   return render_template('pas_rest_accepted_created.html', environment=pas_rest.REST_ENV, message=message, counter=counter, error=error, value=value)

@app.route("/pas_rest_accepted_mpid", methods=['GET', 'POST'])
@login_required
def pas_rest_accepted_mpid():
   message = ""
   counter = 0
   error = ""
   value = ""
   mpid = ""
   if request.method == 'POST':
      mpid = request.form['mpid'] + "*"
      if request.form['mpid'] == "":
         mpid = "*"
      if request.form['mpid'] == "*":
         mpid = "*"
      value = request.form['mpid']
      try:
         message, counter, error = pas_rest.get_accepted_mpid(mpid)
      except:
         message = {'status': 'fail', 'data': {'message': 'Error with REST command!'}}
         counter = ""
         error = ""
         value = ""
   return render_template('pas_rest_accepted_mpid.html', environment=pas_rest.REST_ENV, message=message, counter=counter, error=error, value=value)

@app.route("/pas_rest_accepted_mpinv", methods=['GET', 'POST'])
@login_required
def pas_rest_accepted_mpinv():
   message = ""
   counter = 0
   error = ""
   value = ""
   mpinv = ""
   if request.method == 'POST':
      mpinv = "\"" + request.form['mpinv'] + "\""
      if request.form['mpinv'] == "":
         mpinv = "*"
      if request.form['mpinv'] == "*":
         mpinv = "*"
      value = request.form['mpinv']
      try:
         message, counter, error = pas_rest.get_accepted_mpinv(mpinv)
      except:
         message = {'status': 'fail', 'data': {'message': 'Error with REST command!'}}
         counter = ""
         error = ""
         value = ""
   return render_template('pas_rest_accepted_mpinv.html', environment=pas_rest.REST_ENV, message=message, counter=counter, error=error, value=value)

@app.route("/pas_rest_disseminate_aip", methods=['GET', 'POST'])
@login_required
def pas_rest_disseminate_aip():
   message = ""
   if request.method == 'POST':
      aipid = request.form['aipid']
      message, error = pas_rest.disseminate_aip(aipid)
   return render_template('pas_rest_disseminate_aip.html', environment=pas_rest.REST_ENV, message=message, error=error)

####################################
### MUSEUMPLUS PAS LOG
####################################
@app.route("/paslog_index")
@login_required
def paslog_index():
   return render_template('paslog_index.html', environment=mp_paslog_mod.MP_ENV, environment2=mp_paslog_mod.REST_ENV)

@app.route("/get_csc_paslog")
@login_required
def get_csc_paslog():
   error = ""
   try:
      r_json, counter, error = mp_paslog_mod.get_accepted_created_by_id("*")
      if 'status' in r_json and 'data' in r_json and 'results' in r_json['data']: 
         results = r_json['data']['results'] 
      for result in results: 
         # Check if same ID is already in database
         check_csc_id = db_paslog_csc.query.filter_by(pas_id = result['id']).all()
         if check_csc_id == []: # If same ID not found, then insert to database
            pas_mp_id =result['match']['mets_dmdSec_mdWrap_xmlData_lidoWrap_lido_administrativeMetadata_recordWrap_recordID'][0]
            pas_id = result['id'] 
            if 'lastmoddate' in result:
               pas_created = result['lastmoddate'][-1] 
            else:
               pas_created = result['createdate']
            pas_location = result['location'] 
            paslog_mark = db_paslog_csc(pas_mp_id = pas_mp_id, pas_id = pas_id, pas_created = pas_created, pas_location = pas_location)
            db.session.add(paslog_mark)
            db.session.commit()
         else:
            csc_update = db_paslog_csc.query.filter_by(pas_id = result['id']).first()
            csc_update.pas_mp_id =result['match']['mets_dmdSec_mdWrap_xmlData_lidoWrap_lido_administrativeMetadata_recordWrap_recordID'][0]
            csc_update.pas_id = result['id'] 
            if 'lastmoddate' in result:
               csc_update.pas_created = result['lastmoddate'][-1] 
            else:
               csc_update.pas_created = result['createdate']
            csc_update.pas_location = result['location'] 
            db.session.commit()
   except Exception as e:
      return f'Error reading CSC API: {str(e)}', 500
   objects = r_json #['data']['results']
   return render_template('paslog_csc_accepted.html', totalSize=counter, objects=objects, error=error)

@app.route("/get_mp_paslog")
@login_required
def get_mp_paslog():
   try:
      totalSize, mydict, xml = mp_paslog_mod.get_mp_object_by_paslog()
      for key, value in mydict.items():
         # Check if same ID is already in database
         check_mp_id = db_paslog_mp.query.filter_by(mp_id = key).all()
         if check_mp_id == []: # If same ID not found, then insert to database
            paslog_mark = db_paslog_mp(mp_id = key, mp_name = value["ObjObjectVrt"], mp_paslog = value["ObjPASLog01Clb"])
            db.session.add(paslog_mark)
            db.session.commit()
         else:
            # Update mp_name value if same ID is found
            mp_update = db_paslog_mp.query.filter_by(mp_id=key).first()
            mp_update.mp_name = value["ObjObjectVrt"]
            mp_update.mp_paslog = value["ObjPASLog01Clb"]
            db.session.commit()
         check_csc_mp_id = db_paslog_csc.query.filter_by(pas_mp_id = key).all()
         if check_csc_mp_id == []: # If same ID not found
            pass
         else: # In case same ID found
            csc_update = db_paslog_csc.query.filter_by(pas_mp_id = key).first()
            csc_update.mp_paslog = value["ObjPASLog01Clb"]
            db.session.add(csc_update)
            db.session.commit()
   except Exception as e:
      return f'Error fetching MP data: {str(e)}', 500
   return render_template('paslog_mp_marked.html', totalSize=totalSize, objects=mydict, xml=xml)

@app.route('/paslog_show_data')
@login_required
def paslog_show_data():
   try:
      # Fetch data from the table
      #data = db.session.query(db_paslog_csc).all()
      #data = db.session.query(db_paslog_csc).order_by(db_paslog_csc.mp_paslog.asc(), db_paslog_csc.pas_created.desc()).all()
      data = db.session.query(db_paslog_csc).filter(db_paslog_csc.mp_paslog == None).order_by(db_paslog_csc.mp_paslog.asc(), db_paslog_csc.pas_created.desc()).all()
      db.session.commit()
      totalSize = len(data)
      return render_template('paslog_show_data.html', data=data, totalSize=totalSize)
   except Exception as e:
      return f'Error fetching MP marked data: {str(e)}', 500

@app.route('/paslog_put_mark/', methods=['GET', 'POST'])
@login_required
def paslog_put_mark():
   obj_id = request.args.get('obj_id')
   aipid = request.args.get('aipid')
   timestamp = request.args.get('timestamp')
   response_status = mp_paslog_mod.set_paslog_data(obj_id, aipid, timestamp)
   # Status code 204 = OK, code 400 = Bad request, 403 = Forbidden
   # return f'Status code: {response_status}', 200
   if response_status == 204:
      try:
         #paslog_update = db_paslog_csc.query.filter_by(pas_mp_id=obj_id).first()
         paslog_update = db_paslog_csc.query.filter_by(pas_id=aipid).first()
         paslog_update.mp_paslog = "\"PAS arkistointi: AIP-ID= " + aipid + " " + " Timestamp= " +timestamp + "\""
         db.session.commit()
      except Exception as e:
         return f'Error writing PASLOG data to database: {str(e)}', 500
   return render_template('paslog_put_mark.html', response_status=response_status, obj_id=obj_id, aipid=aipid, timestamp=timestamp)

@app.route("/make_empty_db")
@login_required
def make_empty_db():
   try:
      # Create a session context and use it to delete rows
      with app.app_context():
         db.session.query(db_paslog_mp).delete()
         db.session.query(db_paslog_csc).delete()
         db.session.commit()
      return 'Table truncated successfully', 200
   except Exception as e:
      return f'Error truncating table: {str(e)}', 500
   #return render_template('paslog_db_trunc.html', environment=mp_paslog_mod.MP_ENV)