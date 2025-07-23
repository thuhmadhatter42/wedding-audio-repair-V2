from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import uuid
import json
from datetime import datetime
import logging
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
UPLOAD_FOLDER = 'uploads'
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'mp4', 'm4a', 'aac', 'flac', 'ogg', 'mov', 'avi'}

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('orders', exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_order_id():
    return f"WAR-{str(uuid.uuid4())[:8].upper()}"

def save_order(order_data):
    """Save order data to JSON file"""
    order_file = f"orders/{order_data['order_id']}.json"
    with open(order_file, 'w') as f:
        json.dump(order_data, f, indent=2)
    return order_file

def load_order(order_id):
    """Load order data from JSON file"""
    order_file = f"orders/{order_id}.json"
    if os.path.exists(order_file):
        with open(order_file, 'r') as f:
            return json.load(f)
    return None

@app.route('/health', methods=['GET'])
def health_check():
    # Health check endpoint for Railway deployment - v2
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/test', methods=['GET'])
def test_endpoint():
    return jsonify({"message": "Test endpoint working", "routes": [rule.rule for rule in app.url_map.iter_rules()]})

@app.route('/api/create-order', methods=['POST'])
def create_order():
    """Create a new order after successful file upload"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['customer_email', 'customer_name', 'service_type', 'price']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        order_id = generate_order_id()
        
        order_data = {
            "order_id": order_id,
            "customer_email": data['customer_email'],
            "customer_name": data['customer_name'],
            "service_type": data['service_type'],
            "price": data['price'],
            "rush_delivery": data.get('rush_delivery', False),
            "status": "pending_payment",
            "created_at": datetime.now().isoformat(),
            "file_uploaded": False,
            "payment_completed": False
        }
        
        save_order(order_data)
        
        logger.info(f"Created order {order_id} for {data['customer_email']}")
        
        return jsonify({
            "success": True,
            "order_id": order_id,
            "message": "Order created successfully"
        })
        
    except Exception as e:
        logger.error(f"Error creating order: {str(e)}")
        return jsonify({"error": "Failed to create order"}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file_direct():
    """Handle direct file upload without requiring an order ID first"""
    try:
        # Check if file is in request
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        
        # Check if file is selected
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        # Validate file type
        if not allowed_file(file.filename):
            return jsonify({"error": "Invalid file type. Please upload an audio or video file."}), 400
        
        # Check file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({"error": "File size exceeds 100MB limit"}), 400
        
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        
        # Generate secure filename
        filename = secure_filename(file.filename)
        file_extension = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{file_id}.{file_extension}"
        
        # Save file
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(file_path)
        
        logger.info(f"File uploaded with ID {file_id}: {filename} ({file_size} bytes)")
        
        return jsonify({
            "success": True,
            "message": "File uploaded successfully",
            "file_id": file_id,
            "filename": filename,
            "file_size": file_size
        })
        
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        return jsonify({"error": "Failed to upload file"}), 500

@app.route('/api/upload-file/<order_id>', methods=['POST'])
def upload_file(order_id):
    """Handle file upload for a specific order"""
    try:
        # Check if order exists
        order_data = load_order(order_id)
        if not order_data:
            return jsonify({"error": "Order not found"}), 404
        
        # Check if file is in request
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        
        # Check if file is selected
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        # Validate file type
        if not allowed_file(file.filename):
            return jsonify({"error": "Invalid file type. Please upload an audio or video file."}), 400
        
        # Check file size (Flask has built-in size limit, but we'll add our own check)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({"error": "File size exceeds 100MB limit"}), 400
        
        # Generate secure filename
        filename = secure_filename(file.filename)
        file_extension = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{order_id}_{uuid.uuid4().hex[:8]}.{file_extension}"
        
        # Save file
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(file_path)
        
        # Update order data
        order_data['file_uploaded'] = True
        order_data['file_path'] = file_path
        order_data['original_filename'] = filename
        order_data['file_size'] = file_size
        order_data['uploaded_at'] = datetime.now().isoformat()
        order_data['status'] = 'file_uploaded'
        
        save_order(order_data)
        
        logger.info(f"File uploaded for order {order_id}: {filename} ({file_size} bytes)")
        
        return jsonify({
            "success": True,
            "message": "File uploaded successfully",
            "order_id": order_id,
            "filename": filename,
            "file_size": file_size
        })
        
    except Exception as e:
        logger.error(f"Error uploading file for order {order_id}: {str(e)}")
        return jsonify({"error": "Failed to upload file"}), 500

@app.route('/api/order/<order_id>', methods=['GET'])
def get_order(order_id):
    """Get order details"""
    try:
        order_data = load_order(order_id)
        if not order_data:
            return jsonify({"error": "Order not found"}), 404
        
        # Remove sensitive file path from response
        response_data = order_data.copy()
        if 'file_path' in response_data:
            del response_data['file_path']
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error getting order {order_id}: {str(e)}")
        return jsonify({"error": "Failed to get order"}), 500

@app.route('/api/payment-success/<order_id>', methods=['POST'])
def payment_success(order_id):
    """Mark order as paid"""
    try:
        order_data = load_order(order_id)
        if not order_data:
            return jsonify({"error": "Order not found"}), 404
        
        data = request.get_json() or {}
        
        # Update order status
        order_data['payment_completed'] = True
        order_data['status'] = 'paid'
        order_data['payment_completed_at'] = datetime.now().isoformat()
        
        # Add payment details if provided
        if 'payment_intent_id' in data:
            order_data['payment_intent_id'] = data['payment_intent_id']
        
        save_order(order_data)
        
        logger.info(f"Payment completed for order {order_id}")
        
        return jsonify({
            "success": True,
            "message": "Payment recorded successfully",
            "order_id": order_id
        })
        
    except Exception as e:
        logger.error(f"Error recording payment for order {order_id}: {str(e)}")
        return jsonify({"error": "Failed to record payment"}), 500

@app.route('/api/orders', methods=['GET'])
def list_orders():
    """List all orders (for admin/debugging)"""
    try:
        orders = []
        for filename in os.listdir('orders'):
            if filename.endswith('.json'):
                order_id = filename[:-5]  # Remove .json extension
                order_data = load_order(order_id)
                if order_data:
                    # Remove sensitive data
                    safe_data = {
                        'order_id': order_data['order_id'],
                        'customer_email': order_data['customer_email'],
                        'status': order_data['status'],
                        'created_at': order_data['created_at'],
                        'file_uploaded': order_data.get('file_uploaded', False),
                        'payment_completed': order_data.get('payment_completed', False)
                    }
                    orders.append(safe_data)
        
        return jsonify({"orders": orders})
        
    except Exception as e:
        logger.error(f"Error listing orders: {str(e)}")
        return jsonify({"error": "Failed to list orders"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    app.run(debug=debug, host='0.0.0.0', port=port)