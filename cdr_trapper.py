import os
import re
import json
import logging
import requests
import datetime

# --- CONFIGURATION: Read from Environment Variables ---
# NOTE: These should match the environment variables set in your docker-compose file.
CLIENT_ID = os.environ.get('CLIENT_ID', 'default_client')
ZABBIX_HOST_NAME = os.environ.get('ZABBIX_HOST_NAME', 'Client-1-Log-API')
LOG_API_HOST = os.environ.get('LOG_API_HOST', 'http://127.0.0.1:20051') # Log API Endpoint
CDR_FILE_PATH = os.environ.get('CDR_FILE_PATH', '/var/lib/3cxpbx/Instance1/Data/Logs/CDRLogs/cdr.log')
CHECKPOINT_FILE = os.environ.get('CHECKPOINT_FILE', '/var/log/app/cdr_checkpoint.txt')
ZABBIX_ITEM_KEY = 'mos.actual' # New Zabbix Item Key for Actual MOS

# --- REGEX AND PARSING ---

# This regex is based on the default 3CX CDR format (comma-separated fields)
# We are primarily interested in the 'JitterAvg', 'PacketLossAvg', and 'MOS' fields, 
# which are typically found at the end of the line. The 3CX format is very long, 
# so we match the general structure and capture key fields.
CDR_REGEX = re.compile(
    r'.*,'  # Match everything up to the last fields
    r'(?P<JitterAvg>[\d\.]+),'  # Average Jitter
    r'(?P<PacketLossAvg>[\d\.]+),'  # Average Packet Loss
    r'(?P<MOS>[\d\.]+),'  # MOS score (Actual)
    r'(?P<CallID>[\w-]+),' # Call ID
    r'$' # End of line
)

# --- UTILITY FUNCTIONS ---

def get_last_position(checkpoint_file):
    """Reads the last known file position from the checkpoint file."""
    try:
        with open(checkpoint_file, 'r') as f:
            position = int(f.read().strip())
            logging.debug(f"Read checkpoint position: {position}")
            return position
    except (FileNotFoundError, ValueError):
        # If file doesn't exist or is empty/corrupt, start from 0
        logging.warning("Checkpoint file not found or invalid. Starting from the beginning.")
        return 0

def save_last_position(checkpoint_file, position):
    """Writes the current file position to the checkpoint file."""
    try:
        os.makedirs(os.path.dirname(checkpoint_file) or '.', exist_ok=True)
        with open(checkpoint_file, 'w') as f:
            f.write(str(position))
            logging.debug(f"Saved checkpoint position: {position}")
    except IOError as e:
        logging.error(f"Failed to save checkpoint file {checkpoint_file}: {e}")

def send_to_log_api(value, item_key, zabbix_host, log_api_host):
    """Sends a single metric to the Zabbix Log API."""
    try:
        message = {
            'value': str(value),
            'logtime': datetime.datetime.now().isoformat(),
            'client_id': CLIENT_ID,
            'zabbix_host': zabbix_host,
            'item_key': item_key
        }
        
        url = f"{log_api_host}/log"
        response = requests.post(url, json=message, timeout=10)
        response.raise_for_status()
        logging.info(f"Successfully sent {item_key}={value} to Log API.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending data to Log API at {url}: {e}")

# --- MAIN LOGIC ---

def parse_new_cdr_records():
    """Reads new CDR records, calculates the average MOS, and sends it to the API."""
    logging.info(f"Starting CDR parsing for file: {CDR_FILE_PATH}")
    
    last_position = get_last_position(CHECKPOINT_FILE)
    new_mos_scores = []
    
    try:
        with open(CDR_FILE_PATH, 'r') as f:
            # Move to the last saved position
            f.seek(last_position)
            
            # Read new lines from the file
            new_lines = f.readlines()
            
            for line in new_lines:
                match = CDR_REGEX.search(line)
                if match:
                    # Extract the actual MOS value reported by 3CX
                    mos_value = float(match.group('MOS'))
                    
                    # 3CX MOS is often an R-Factor, typically a value from 0 to 100.
                    # We will send this raw score as 'mos.actual'
                    if mos_value > 0:
                        new_mos_scores.append(mos_value)
                        
            # Save the new file position, which is the current end of the file
            current_position = f.tell()
            save_last_position(CHECKPOINT_FILE, current_position)

    except FileNotFoundError:
        logging.error(f"CDR log file not found at: {CDR_FILE_PATH}")
        return
    except Exception as e:
        logging.error(f"An unexpected error occurred during file reading or parsing: {e}")
        # Do NOT update the checkpoint in case of an error, so we retry the data next time
        return

    # Process the new scores
    if new_mos_scores:
        # Calculate the average of all new MOS scores found since the last run
        average_mos = sum(new_mos_scores) / len(new_mos_scores)
        logging.info(f"Found {len(new_mos_scores)} new CDR records. Average Actual MOS: {average_mos:.2f}")
        
        # Send the average actual MOS to the Log API
        send_to_log_api(f"{average_mos:.2f}", ZABBIX_ITEM_KEY, ZABBIX_HOST_NAME, LOG_API_HOST)
    else:
        logging.info("No new CDR records found since last run.")


if __name__ == '__main__':
    # Configure logging for the script itself
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Check for mandatory file paths
    if not os.path.exists(CDR_FILE_PATH):
        logging.error(f"CRITICAL: 3CX CDR log file not found at {CDR_FILE_PATH}. Aborting.")
    else:
        parse_new_cdr_records()
