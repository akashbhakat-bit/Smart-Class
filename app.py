import os
from dotenv import load_dotenv
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VideoGrant, ChatGrant
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
from flask import Flask, flash, request, redirect, url_for, render_template, abort

from deepface import DeepFace
import pandas as pd
from pathlib import Path
import cv2

load_dotenv()
twilio_account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
twilio_api_key_sid = os.environ.get('TWILIO_API_KEY_SID')
twilio_api_key_secret = os.environ.get('TWILIO_API_KEY_SECRET')
twilio_client = Client(twilio_api_key_sid, twilio_api_key_secret,
                       twilio_account_sid)

app = Flask(__name__)


def get_chatroom(name):
    for conversation in twilio_client.conversations.conversations.stream():
        if conversation.friendly_name == name:
            return conversation

    # a conversation with the given name does not exist ==> create a new one
    return twilio_client.conversations.conversations.create(
        friendly_name=name)

@app.route('/login', methods=['POST'])
def login():
    username = request.get_json(force=True).get('username')
    if not username:
        abort(401)

    conversation = get_chatroom('My Room')
    try:
        conversation.participants.create(identity=username)
    except TwilioRestException as exc:
        # do not error if the user is already in the conversation
        if exc.status != 409:
            raise

    token = AccessToken(twilio_account_sid, twilio_api_key_sid,
                        twilio_api_key_secret, identity=username)
    token.add_grant(VideoGrant(room='My Room'))
    token.add_grant(ChatGrant(service_sid=conversation.chat_service_sid))

    return {'token': token.to_jwt().decode(),
            'conversation_sid': conversation.sid}


#################################################################################

app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///registration.db"
app.config['SQLALCHEMY_BINDS']={'two':"sqlite:///attendance.db",
                                'three':"sqlite:///emotion.db",
                                'four':"sqlite:///login.db"

}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
now = datetime.now()


class SignUp(db.Model):
    name = db.Column(db.String(200), primary_key=True)
    role= db.Column(db.String(200), nullable=False, default="student")
    email = db.Column(db.String(200), primary_key=True)
    def __repr__(self) -> str:
        return f"{self.name} - {self.role} - {self.email} "

class Attendance(db.Model):
    __bind_key__='two'
    name = db.Column(db.String(200), primary_key=True)
    attend= db.Column(db.String(200), nullable=False, default="Present")
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"{self.name} - {self.attend}"

class Emotions(db.Model):
    __bind_key__='three'
    name = db.Column(db.String(200), primary_key=True)
    emotion= db.Column(db.String(200), nullable=False, default="Normal")
    attention= db.Column(db.String(200), nullable=False, default="Yes")
    date_created = db.Column(db.DateTime, default=datetime.utcnow)


    def __repr__(self) -> str:
        return f"{self.name} - {self.emotion} - {self.attention} "

class Login(db.Model):
    __bind_key__='four'
    email = db.Column(db.String(200), primary_key=True)
    password= db.Column(db.String(200), nullable=False)
    role= db.Column(db.String(200), nullable=False, default="student")

    def __repr__(self) -> str:
        return f"{self.email} - {self.password} - {self.role}"


@app.route('/')
def index():
    return render_template('login.html')

@app.route('/signup_call')
def sign_up_call():
    return render_template('signup.html')

new_user_name="none"
directory = 'database'

UPLOAD_FOLDER = 'templates'
 
app.secret_key = "secret key"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
 
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg', 'gif'])
 
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/signup_user', methods=['POST'])
def signup_user():
    if request.method=='POST':
        name = request.form['name']
        role= request.form['role']
        email = request.form['email']
        password= request.form['password']
        signup = SignUp(name=name, role=role,email=email)
        db.session.add(signup)
        db.session.commit()
        login = Login(email=email, password=password,role=role)
        db.session.add(login)
        db.session.commit()
        new_user_name=name
    return render_template('login.html')


@app.route('/signup_user_photo', methods=['POST'])
def signup_user_photo():
    if(new_user_name!="none"):
        
        path_to_save='database/'+new_user_name
        pathlib.Path(path_to_save).mkdir(parents=True, exist_ok=True) 
        app.config['UPLOAD_FACE_FOLDER']=path_to_save
        if request.method == 'POST':
            # check if the post request has the file part
            if 'file' not in request.files:
                flash('No file part')
                return redirect(request.url)
            file = request.files['file']
            # if user does not select file, browser also
            # submit a empty part without filename
            if file.filename == '':
                flash('No selected file')
                return redirect(request.url)
            if file and allowed_file(file.filename):
                #filename = secure_filename(file.filename)
                file_name=new_user_name+""+".jpg"
                file.save(os.path.join(app.config['UPLOAD_FACE_FOLDER'], file_name))
                
                return render_template('login.html')
            else:
                return render_template('signup.html')

    

@app.route('/login_user', methods=['POST'])
def login_user():
    if request.method=='POST':
        
        email = request.form['email']
        password = request.form['password']
        try:
            login = Login.query.filter_by(email=email).first()
            role=login.role
            if(login.password==password):
                signup_data = SignUp.query.filter_by(email=email).first()
                name=signup_data.name
                return render_template('index.html',role=role,name=name)


        except:
            return render_template('login.html')

@app.route('/show_detailed_info/<string:name>', methods=['POST'])
def see_student_info(name):
    if request.method=='POST':
        emotions = Emotions.query.filter_by(name=name).all() 
        return render_template('footer.html', emotions=emotions,show_detail=1)

        
@app.route('/see_student_info_presents', methods=['POST'])
def see_student_info_presents():
    if request.method=='POST':
        attendance = Attendance.query.all() 
        return render_template('footer.html', attendance=attendance,show_present=1)




#@app.route('/image_for_review', methods=['POST'])
#def image_for_review():
#    if request.method=='POST':
        


if __name__ == '__main__':
    app.run(debug=False)
