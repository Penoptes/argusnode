import logging
import json
import re
import os
import datetime
from flask import Flask, request, jsonify
from subprocess import run, PIPE, STDOUT

# --- Configuration: Read from Environment Variables ---
CLIENT_ID = os.environ.get('CLIENT_ID', 'default_client')
# The ZABBIX_HOST_NAME must match the 'Host name' defined in Zabbix for the host object.
ZABBIX_HOST_NAME = os.environ.get('ZABBIX_HOST_NAME', 'Client-1-Log-API')
# ZABBIX_SERVER_IP is the internal Docker name of the Zabbix Server container.
ZABBIX_SERVER_SERVICE = os.environ.get('ZABBIX_SERVER_IP', 'zabbix-server')
ZABBIX_SERVER_PORT = os.environ.get('ZABBIX_SERVER_PORT', '10051')

# The log file path, including the CLIENT_ID for better organization
LOG_FILE = f'/var/log/app/{CLIENT_ID}_remote_logs.log'

# --- Metric Definitions and Regex Patterns ---
# Each dictionary entry maps the Zabbix Item Key to the regex pattern
# that extracts its value from the incoming log message.
METRIC_CONFIG = {
    # Keys MUST match the Zabbix Trapper Item Key configuration
    'mos.rating': re.compile(r'mos=(\d+\.?\d*)', re.IGNORECASE),
    'voip.latency': re.compile(r'rtt=(\d+\.?\d*)', re.IGNORECASE),
    'voip.jitter': re.compile(r'jitter=(\d+\.?\d*)', re.IGNORECASE),
    'voip.loss': re.compile(r'loss=(\d+\.?\d*)', re.IGNORECASE)
}

# --- Configure Logging ---
# Setting up logging to the dedicated file
file_handler = logging.FileHandler(LOG_FILE)
formatter = logging.Formatter('%(asctime)s | REMOTE_LOG | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)

app = Flask(__name__)

def send_to_zabbix(key, value):
    """
    Constructs and executes the zabbix_sender command to send a single key-value pair.
    """
    try:
        command = [
            'zabbix_sender',
            '-z', ZABBIX_SERVER_SERVICE,  # Zabbix Server Host/IP (e.g., zabbix-server)
            '-p', ZABBIX_SERVER_PORT,     # Zabbix Server Port (default 10051)
            '-s', ZABBIX_HOST_NAME,       # Hostname in Zabbix (e.g., Client-1-Log-API)
            '-k', key,                    # Item Key (e.g., mos.rating)
            '-o', str(value)              # Value
        ]
        
        # Execute the command with a timeout
        result = run(command, stdout=PIPE, stderr=PIPE, universal_newlines=True, timeout=5)

        if result.returncode != 0:
            logger.error(f"Zabbix Sender failed for {key}={value}: {result.stderr.strip()}")
            return False, result.stderr.strip()
        
        # Check Zabbix Sender output for success/failure in the summary
        # If 'processed: 1; failed: 0' appears, it was successful.
        if "failed: 0" in result.stdout and "processed: 1" in result.stdout:
            logger.info(f"Successfully sent {key}={value} to Zabbix. Result: {result.stdout.strip()}")
            return True, result.stdout.strip()
        else:
            # This handles cases where zabbix_sender runs but Zabbix rejects the data (e.g., unsupported item type)
            logger.warning(f"Zabbix Sender partial failure for {key}={value}: {result.stdout.strip()}")
            return False, result.stdout.strip()

    except Exception as e:
        logger.error(f"Exception during zabbix_sender execution for {key}: {e}")
        return False, str(e)


@app.route('/log', methods=['POST'])
def log_message():
    """Accepts a POST request with JSON data, logs the message, parses metrics, and sends to Zabbix."""
    if not request.is_json:
        return jsonify({"error": "Missing or non-JSON body"}), 400

    data = request.get_json()
    message = data.get('message', '')

    if not message:
        return jsonify({"error": "JSON body must contain a 'message' field"}), 400

    # 1. Log the received message to the file
    logger.info(f"Received from probe: {message}")

    metrics_sent_count = 0
    metrics_failed_count = 0
    
    # 2. Parse metrics and send to Zabbix
    for key, pattern in METRIC_CONFIG.items():
        match = pattern.search(message)
        if match:
            value = match.group(1)
            # Try to send the metric to Zabbix
            success, result_msg = send_to_zabbix(key, value)
            
            if success:
                metrics_sent_count += 1
            else:
                metrics_failed_count += 1

    summary_msg = (
        f"Log received. Sent {metrics_sent_count} metrics to Zabbix "
        f"for host {ZABBIX_HOST_NAME}. Failed: {metrics_failed_count}."
    )
    
    # 3. Return response to the probe script
    if metrics_failed_count > 0:
         # Return HTTP 500 if critical metrics failed to send, or 200 with warning
         return jsonify({"status": "warning", "message": summary_msg}), 200
    else:
        return jsonify({"status": "success", "message": summary_msg}), 200

@app.route('/')
def status():
    """Simple status check."""
    return jsonify({
        "status": "running", 
        "service": "Remote Log Server",
        "client_id": CLIENT_ID,
        "zabbix_target": ZABBIX_HOST_NAME
    }), 200

if __name__ == '__main__':
    # Flask will run on all interfaces (0.0.0.0) on port 8080 inside the container.
    app.run(host='0.0.0.0', port=8080, threaded=True)
