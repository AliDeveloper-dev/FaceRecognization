import cv2
import numpy as np
import os
import pickle
import time
import json
from datetime import datetime
import threading
import base64
from io import BytesIO

# Flask imports
from flask import Flask, render_template, request, jsonify, Response, session
from flask_cors import CORS
import requests

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this!
CORS(app)

class FaceSecuritySystem:
    def __init__(self):
        self.face_recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        self.labels = {}
        self.label_names = {}
        self.camera = None
        
        # Create directories
        self.create_directories()
        self.load_data()
        
        # Security settings
        self.failed_attempts = {}
        self.locked_users = {}
        
        # Webhook/API settings (for integration)
        self.webhook_url = None  # Set your webhook URL here
        
    def create_directories(self):
        """Create necessary directories"""
        dirs = ['static/faces', 'static/models', 'static/intruders', 'static/logs', 'templates']
        for dir_path in dirs:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
    
    def load_data(self):
        """Load face data"""
        model_file = 'static/models/face_model.yml'
        labels_file = 'static/models/labels.pkl'
        
        if os.path.exists(model_file):
            self.face_recognizer.read(model_file)
        
        if os.path.exists(labels_file):
            with open(labels_file, 'rb') as f:
                self.labels = pickle.load(f)
            self.label_names = {v: k for k, v in self.labels.items()}
    
    def save_data(self):
        """Save face data"""
        self.face_recognizer.write('static/models/face_model.yml')
        with open('static/models/labels.pkl', 'wb') as f:
            pickle.dump(self.labels, f)
    
    def get_camera(self):
        """Get camera instance"""
        if self.camera is None or not self.camera.isOpened():
            self.camera = cv2.VideoCapture(0)
        return self.camera
    
    def release_camera(self):
        """Release camera"""
        if self.camera:
            self.camera.release()
            self.camera = None
    
    def capture_frame(self):
        """Capture a frame from camera"""
        camera = self.get_camera()
        ret, frame = camera.read()
        return ret, frame
    
    def train_model(self):
        """Train face recognition model"""
        faces = []
        labels = []
        
        for person_name in os.listdir('static/faces'):
            person_path = f'static/faces/{person_name}'
            
            if os.path.isdir(person_path):
                if person_name not in self.labels:
                    self.labels[person_name] = len(self.labels)
                
                person_id = self.labels[person_name]
                
                for img_name in os.listdir(person_path):
                    img_path = os.path.join(person_path, img_name)
                    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                    
                    if img is not None:
                        faces.append(img)
                        labels.append(person_id)
        
        if faces:
            self.face_recognizer.train(faces, np.array(labels))
            self.save_data()
            self.label_names = {v: k for k, v in self.labels.items()}
            return True
        return False
    
    def recognize_face_from_frame(self, frame):
        """Recognize face from a frame"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        
        for (x, y, w, h) in faces:
            face_roi = gray[y:y+h, x:x+w]
            face_roi = cv2.resize(face_roi, (200, 200))
            
            label_id, confidence = self.face_recognizer.predict(face_roi)
            
            if confidence < 70:  # Good match
                user_name = self.label_names.get(label_id, "Unknown")
                if user_name != "Unknown":
                    return True, user_name, confidence, (x, y, w, h)
        
        return False, "Unknown", 100, None
    
    def add_user(self, name, images):
        """Add new user with images"""
        person_folder = f'static/faces/{name}'
        if not os.path.exists(person_folder):
            os.makedirs(person_folder)
        
        # Save images
        for i, image_data in enumerate(images):
            # Convert base64 to image
            if ',' in image_data:
                image_data = image_data.split(',')[1]
            
            img_bytes = base64.b64decode(image_data)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            
            if img is not None:
                img_path = os.path.join(person_folder, f'{name}_{i}.jpg')
                cv2.imwrite(img_path, img)
        
        # Train model with new data
        self.train_model()
        return True
    
    def capture_intruder(self, frame):
        """Save intruder image"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"static/intruders/intruder_{timestamp}.jpg"
        cv2.imwrite(filename, frame)
        return filename
    
    def send_webhook(self, event_type, data):
        """Send webhook notification"""
        if self.webhook_url:
            payload = {
                'event': event_type,
                'timestamp': datetime.now().isoformat(),
                'data': data
            }
            try:
                requests.post(self.webhook_url, json=payload, timeout=5)
            except:
                pass

# Create system instance
face_system = FaceSecuritySystem()

# ==============================================
# FLASK ROUTES
# ==============================================

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')

@app.route('/login')
def login_page():
    """Login page"""
    return render_template('login.html')

@app.route('/admin')
def admin_page():
    """Admin panel"""
    users = list(face_system.labels.keys())
    return render_template('admin.html', users=users)

@app.route('/api/check_status')
def check_status():
    """Check system status"""
    return jsonify({
        'status': 'online',
        'users_count': len(face_system.labels),
        'system_time': datetime.now().isoformat()
    })

@app.route('/api/recognize_face', methods=['POST'])
def recognize_face():
    """Recognize face from uploaded image"""
    try:
        # Get image from request
        image_data = request.json.get('image')
        if not image_data:
            return jsonify({'error': 'No image provided'}), 400
        
        # Convert base64 to image
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        
        img_bytes = base64.b64decode(image_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Recognize face
        recognized, username, confidence, bbox = face_system.recognize_face_from_frame(frame)
        
        if recognized:
            # Reset failed attempts for this user
            face_system.failed_attempts[username] = 0
            
            # Log successful login
            log_entry = {
                'user': username,
                'type': 'face_login',
                'time': datetime.now().isoformat(),
                'confidence': float(100 - confidence),
                'status': 'success'
            }
            
            # Send webhook
            face_system.send_webhook('face_login_success', log_entry)
            
            return jsonify({
                'success': True,
                'user': username,
                'confidence': float(100 - confidence),
                'message': f'Welcome {username}!'
            })
        else:
            # Increment failed attempts
            ip_address = request.remote_addr
            face_system.failed_attempts[ip_address] = face_system.failed_attempts.get(ip_address, 0) + 1
            
            # Capture intruder if too many attempts
            if face_system.failed_attempts[ip_address] >= 3:
                intruder_image = face_system.capture_intruder(frame)
                
                # Send webhook alert
                alert_data = {
                    'ip': ip_address,
                    'attempts': face_system.failed_attempts[ip_address],
                    'image_path': intruder_image,
                    'time': datetime.now().isoformat()
                }
                face_system.send_webhook('intruder_alert', alert_data)
            
            return jsonify({
                'success': False,
                'message': 'Face not recognized',
                'attempts': face_system.failed_attempts.get(ip_address, 0)
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/add_user', methods=['POST'])
def add_user():
    """Add new user"""
    try:
        name = request.form.get('name')
        images = request.form.getlist('images[]')
        
        if not name or not images:
            return jsonify({'error': 'Name and images required'}), 400
        
        success = face_system.add_user(name, images)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'User {name} added successfully'
            })
        else:
            return jsonify({'error': 'Failed to add user'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/train_model', methods=['POST'])
def train_model():
    """Train the face model"""
    try:
        success = face_system.train_model()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Model trained successfully',
                'users_count': len(face_system.labels)
            })
        else:
            return jsonify({'error': 'No faces to train'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_users')
def get_users():
    """Get list of registered users"""
    users = list(face_system.labels.keys())
    return jsonify({
        'success': True,
        'users': users,
        'count': len(users)
    })

@app.route('/api/unlock_device', methods=['POST'])
def unlock_device():
    """Simulate device unlock"""
    try:
        device = request.json.get('device', 'general')
        user = request.json.get('user', 'Unknown')
        
        unlock_actions = {
            'phone': f'📱 Mobile phone unlocked for {user}',
            'laptop': f'💻 Laptop unlocked for {user}',
            'website': f'🌐 Secure website accessed by {user}',
            'door': f'🚪 Smart door opened for {user}',
            'general': f'🔓 System unlocked for {user}'
        }
        
        message = unlock_actions.get(device, unlock_actions['general'])
        
        # Log unlock event
        log_entry = {
            'user': user,
            'device': device,
            'time': datetime.now().isoformat(),
            'ip': request.remote_addr
        }
        face_system.send_webhook('device_unlocked', log_entry)
        
        return jsonify({
            'success': True,
            'message': message,
            'device': device,
            'user': user,
            'time': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/video_feed')
def video_feed():
    """Video streaming route"""
    def generate():
        camera = cv2.VideoCapture(0)
        
        while True:
            success, frame = camera.read()
            if not success:
                break
            
            # Do face detection on frame
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_system.face_cascade.detectMultiScale(gray, 1.3, 5)
            
            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            
            # Encode frame as JPEG
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    
    return Response(generate(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/capture_images', methods=['POST'])
def capture_images():
    """Capture multiple images for registration"""
    try:
        name = request.json.get('name')
        count = int(request.json.get('count', 5))
        
        if not name:
            return jsonify({'error': 'Name required'}), 400
        
        images = []
        camera = cv2.VideoCapture(0)
        
        for i in range(count):
            ret, frame = camera.read()
            if ret:
                # Convert to base64
                _, buffer = cv2.imencode('.jpg', frame)
                img_str = base64.b64encode(buffer).decode('utf-8')
                images.append(f"data:image/jpeg;base64,{img_str}")
            
            time.sleep(0.5)  # Wait between captures
        
        camera.release()
        
        return jsonify({
            'success': True,
            'images': images,
            'count': len(images)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

app.run(host='0.0.0.0', port=5000, debug=True)