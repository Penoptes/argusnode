import re
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from subprocess import run, PIPE, STDOUT
import os

app = Flask(__name__)

# --- Configuration: Read from Environment Variables ---
CLIENT_ID = os.environ.get('CLIENT_ID', 'default_client')
ZABBIX_TARGET_HOST = os.environ.get('ZABBIX_HOST_NAME', 'Client-1-Log-API')

# Static Zabbix Configuration
ZABBIX_SERVER_SERVICE = 'zabbix-server'
LOG_FILE_PATH = f'/var/log/app/{CLIENT_ID}_remote_logs.log'

# --- NEW: Define all metrics and their regex patterns ---
# Each dictionary entry maps the Zabbix Item Key to the regex pattern
# that extracts its value from the incoming log message.
METRIC_CONFIG = {
    # Key: 'mos=X.X'
    'mos.rating': re.compile(r'mos=(\d+\.?\d*)', re.IGNORECASE),
    # Key: 'rtt=Y'
    'voip.latency': re.compile(r'rtt=(\d+\.?\d*)', re.IGNORECASE),
    # Key: 'jitter=Z'
    'voip.jitter': re.compile(r'jitter=(\d+\.?\d*)', re.IGNORECASE),
    # Key: 'loss=A'
    'voip.loss': re.compile(r'loss=(\d+\.?\d*)', re.IGNORECASE)
}

# Configure basic logging for the Python script itself
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | APP_API | %(levelname)s | [%(client_id)s] | %(message)s'
)
# Inject CLIENT_ID into the logging context
logger = logging.getLogger(__name__)
logger = logging.LoggerAdapter(logger, {'client_id': CLIENT_ID})


def send_to_zabbix(host, key, value):
    """Sends a single data point to the Zabbix Trapper item."""
    try:
        # Construct the zabbix_sender command
        command = [
            'zabbix_sender',
            '-z', ZABBIX_SERVER_SERVICE,    # Zabbix Server service name
            '-p', '10051',                # Default Zabbix Server Trapper port
            '-s', host,                  # Dynamic Zabbix Host name
            '-k', key,
            '-o', str(value)
        ]

        # Execute the command
        result = run(command, check=True, stdout=PIPE, stderr=PIPE, text=True)

        # Log success/failure
        if "info: 1" in result.stdout:
            logger.info(f"Successfully sent to Zabbix: {host}/{key} = {value}")
        else:
            logger.warning(f"Zabbix sender partial failure or unexpected response: {result.stdout.strip()}")

    except Exception as e:
        logger.error(f"Failed to send data to Zabbix for key {key}: {e}")


@app.route('/log', methods=['POST'])
def receive_log():
    try:
        # 1. Get and Validate Data
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({"status": "error", "message": "Missing 'message' field"}), 400

        message = data['message']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"{timestamp} | REMOTE_LOG | {message}\n"

        # 2. Write to Persistent Log File
        try:
            with open(LOG_FILE_PATH, 'a') as f:
                f.write(log_entry)
        except Exception as e:
            logger.error(f"Error writing to log file {LOG_FILE_PATH}: {e}")
            # Do not stop processing, proceed to Zabbix submission if possible

        # 3. Extract ALL Metrics and Send to Zabbix Trappers
        data_sent = 0
        for key, regex in METRIC_CONFIG.items():
            match = regex.search(message)
            if match:
                try:
                    value = float(match.group(1))
                    send_to_zabbix(ZABBIX_TARGET_HOST, key, value)
                    data_sent += 1
                except ValueError:
                    logger.warning(f"Could not convert '{match.group(1)}' to float for key {key}.")
            else:
                # This is common if a log message doesn't contain all metrics, but we log for tracking
                logger.debug(f"Metric {key} not found in log message.")


        if data_sent == 0:
            logger.info("No VoIP metrics were found in the log message. Skipping all Zabbix submissions.")


        return jsonify({"status": "success", "message": f"Log received for {CLIENT_ID} and {data_sent} metrics processed."})

    except Exception as e:
        logger.error(f"Unhandled error in receive_log: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
