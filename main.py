from flask import Flask, render_template, request, jsonify, session
from datetime import datetime
import json
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Змініть на свій ключ

# ============ МОДЕЛИ ДАНИХ ============
class DroneData:
    def __init__(self, model, serial):
        self.model = model
        self.serial = serial
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'model': self.model,
            'serial': self.serial,
            'timestamp': self.timestamp
        }

class FlightData:
    def __init__(self, drone_model, serial, location, duration, altitude, notes=""):
        self.id = int(datetime.now().timestamp() * 1000)
        self.drone = drone_model
        self.serial = serial
        self.location = location
        self.duration = int(duration)
        self.altitude = int(altitude)
        self.notes = notes
        self.timestamp = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
    
    def to_dict(self):
        return {
            'id': self.id,
            'drone': self.drone,
            'serial': self.serial,
            'location': self.location,
            'duration': self.duration,
            'altitude': self.altitude,
            'notes': self.notes,
            'timestamp': self.timestamp
        }

# ============ МАРШУТИ СТОРІНОК ============
@app.route('/')
def index():
    return render_template('index.html')

# ============ API: АУТЕНТИФІКАЦІЯ ============
@app.route('/api/login', methods=['POST'])
def api_login():
    """Вхід користувача"""
    try:
        data = request.get_json()
        
        # Валідація
        required_fields = ['name', 'email', 'password']
        if not all(field in data for field in required_fields):
            return jsonify({'success': False, 'message': 'Заповніть усі обов\'язкові поля'}), 400
        
        if '@' not in data['email']:
            return jsonify({'success': False, 'message': 'Невірний формат email'}), 400
        
        # Зберегти в сесію
        session['user'] = {
            'name': data['name'].strip(),
            'email': data['email'].strip(),
            'phone': data.get('phone', '').strip()
        }
        
        return jsonify({
            'success': True,
            'message': f'Ласкаво просимо, {data["name"]}!',
            'user': session['user']
        })
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Помилка: {str(e)}'}), 500

@app.route('/api/logout', methods=['POST'])
def api_logout():
    """Вихід користувача"""
    session.clear()
    return jsonify({'success': True, 'message': 'Ви вийшли з системи'})

# ============ API: ДРОНИ ============
@app.route('/api/drones', methods=['GET'])
def get_drones():
    """Отримати список дронів для сеансу"""
    drones = session.get('session_drones', [])
    return jsonify({'drones': drones})

@app.route('/api/drones', methods=['POST'])
def add_drone():
    """Додати дрон до сеансу"""
    try:
        data = request.get_json()
        
        if not data.get('model') or not data.get('serial'):
            return jsonify({'success': False, 'message': 'Модель і серійний номер обов\'язкові'}), 400
        
        drone = DroneData(data['model'], data['serial'])
        
        # Додати до сеансу
        session_drones = session.get('session_drones', [])
        
        # Перевірити, чи такий дрон вже існує
        exists = any(d['model'] == drone.model and d['serial'] == drone.serial for d in session_drones)
        if not exists:
            session_drones.append(drone.to_dict())
            session['session_drones'] = session_drones
        
        return jsonify({
            'success': True,
            'message': f'Дрон {data["model"]} додано',
            'drone': drone.to_dict()
        })
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Помилка: {str(e)}'}), 500

# ============ API: ПОЛЬОТИ ============
@app.route('/api/flights', methods=['GET'])
def get_flights():
    """Отримати всі польоти"""
    flights = session.get('flights', [])
    return jsonify({'flights': flights})

@app.route('/api/flights', methods=['POST'])
def add_flight():
    """Додати новий політ"""
    try:
        data = request.get_json()
        
        # Валідація
        required_fields = ['drone_model', 'serial', 'location', 'duration', 'altitude']
        if not all(field in data for field in required_fields):
            return jsonify({'success': False, 'message': 'Заповніть усі обов\'язкові поля'}), 400
        
        flight = FlightData(
            drone_model=data['drone_model'],
            serial=data['serial'],
            location=data['location'],
            duration=data['duration'],
            altitude=data['altitude'],
            notes=data.get('notes', '')
        )
        
        # Додати до сеансу
        flights = session.get('flights', [])
        flights.append(flight.to_dict())
        session['flights'] = flights
        
        return jsonify({
            'success': True,
            'message': 'Зліт успішно додано',
            'flight': flight.to_dict()
        })
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Помилка: {str(e)}'}), 500

@app.route('/api/flights/<int:flight_id>', methods=['DELETE'])
def delete_flight(flight_id):
    """Видалити політ"""
    try:
        flights = session.get('flights', [])
        flights = [f for f in flights if f['id'] != flight_id]
        session['flights'] = flights
        
        return jsonify({'success': True, 'message': 'Зліт видалено'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Помилка: {str(e)}'}), 500

# ============ API: ПОВІДОМЛЕННЯ ============
@app.route('/api/message/generate', methods=['GET'])
def generate_message():
    """Згенерувати повідомлення для Telegram"""
    try:
        user = session.get('user')
        flights = session.get('flights', [])
        session_drones = session.get('session_drones', [])
        
        message = "📋 *ЗВІТ ПРО ПОЛЬОТИ ДРОНІВ*\n\n"
        
        if user:
            message += f"👤 *Оператор:* {user['name']}\n"
            message += f"📧 *Email:* {user['email']}\n"
            if user.get('phone'):
                message += f"📞 *Телефон:* {user['phone']}\n"
            message += "\n"
        
        if session_drones:
            message += "🚁 *Дрони в цьому сеансі:*\n"
            for drone in session_drones:
                message += f"   • {drone['model']} (SN: {drone['serial']})\n"
            message += "\n"
        
        if flights:
            message += f"✈️ *Всього злітів:* {len(flights)}\n\n"
            message += "*Деталі польотів:*\n"
            
            for idx, flight in enumerate(flights, 1):
                message += f"\n{idx}. *{flight['location']}*\n"
                message += f"   Дрон: {flight['drone']}\n"
                message += f"   Серійний номер: `{flight['serial']}`\n"
                message += f"   Тривалість: {flight['duration']} хв.\n"
                message += f"   Висота: {flight['altitude']} м\n"
                if flight.get('notes'):
                    message += f"   Примітки: {flight['notes']}\n"
        else:
            message += "⚠️ *Жодного польоту не записано*"
        
        message += f"\n\n📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        return jsonify({'success': True, 'message': message})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Помилка: {str(e)}'}), 500

@app.route('/api/message/send-telegram', methods=['POST'])
def send_telegram():
    """Надіслати повідомлення в Telegram"""
    try:
        import requests
        
        data = request.get_json()
        token = data.get('token', '').strip()
        chat_id = data.get('chat_id', '').strip()
        message = data.get('message', '').strip()
        
        if not token or not chat_id or not message:
            return jsonify({'success': False, 'message': 'Заповніть усі поля'}), 400
        
        # API Telegram
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        
        response = requests.post(url, json={
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }, timeout=10)
        
        result = response.json()
        
        if result.get('ok'):
            return jsonify({
                'success': True,
                'message': 'Повідомлення надіслано в Telegram'
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Помилка Telegram: {result.get("description", "Unknown error")}'
            }), 400
    
    except requests.exceptions.RequestException as e:
        return jsonify({'success': False, 'message': f'Помилка мережі: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': f'Помилка: {str(e)}'}), 500

# ============ ОБРОБКА ПОМИЛОК ============
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Сторінка не знайдена'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Помилка сервера'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)