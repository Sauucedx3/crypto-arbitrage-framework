from flask import current_app as app, jsonify, request, render_template, flash, redirect, url_for
from .forms import AppConfigForm
import json
import yaml # For prettier YAML output
import os # For log/history file reading
from collections import deque # For reading last N lines efficiently

@app.route('/')
def home():
    # Redirect to the new comprehensive dashboard
    return redirect(url_for('dashboard_route'))


@app.route('/start_arbitrage', methods=['POST'])
def start_arbitrage_route():
    if app.runner is None:
        return jsonify({"error": "ArbitrageRunner not initialized. Check server logs for details on import or initialization errors."}), 500
    
    # Check status directly from runner, which now includes process liveness check
    current_status_info = app.runner.get_status()
    if current_status_info.get('status') == "running" or current_status_info.get('process_alive'):
        return jsonify({"error": "Arbitrage process already running or starting.", "status": current_status_info}), 400
    
    parameter_message = "default"
    if request.is_json:
        params_override = request.get_json()
        if params_override and isinstance(params_override, dict):
            try:
                app.runner.set_optimizer_parameters(params_override) # This method should exist in ArbitrageRunner
                parameter_message = "custom"
                app.logger.info(f"Custom optimizer parameters applied for this run: {params_override}")
            except Exception as e_set_params:
                app.logger.error(f"Error setting optimizer parameters: {e_set_params}")
                # Decide if this is a fatal error or if runner should proceed with defaults
                return jsonify({"error": f"Error applying optimizer parameters: {str(e_set_params)}", "status": app.runner.get_status()}), 400
        elif params_override is not None: # Received JSON, but it's not a dict or it's empty
             app.logger.warning("Received non-dict or empty JSON payload for optimizer params. Using defaults.")
             # Optionally, could return a 400 error if payload is present but malformed in a way that's not None/empty dict
    
    try:
        app.runner.start() 
        return jsonify({"message": f"Arbitrage process initiated with {parameter_message} parameters.", "status": app.runner.get_status()})
    except Exception as e:
        app.logger.error(f"Failed to start arbitrage process: {str(e)}")
        return jsonify({"error": f"Failed to start arbitrage process: {str(e)}", "status": app.runner.get_status()}), 500

@app.route('/stop_arbitrage', methods=['POST'])
def stop_arbitrage_route():
    if app.runner is None:
        return jsonify({"error": "ArbitrageRunner not initialized."}), 500

    current_status_info = app.runner.get_status()
    if not current_status_info.get('process_alive') and current_status_info.get('status') not in ['running', 'starting', 'stopping']:
         return jsonify({"error": "Arbitrage process is not running or already stopped.", "status": current_status_info}), 400

    try:
        app.runner.stop()
        # time.sleep(0.5) # Allow time for process to acknowledge stop
        return jsonify({"message": "Arbitrage process stopping sequence initiated.", "status": app.runner.get_status()})
    except Exception as e:
        return jsonify({"error": f"Failed to stop arbitrage process: {str(e)}", "status": app.runner.get_status()}), 500

@app.route('/arbitrage_status', methods=['GET'])
def arbitrage_status_route():
    if app.runner is None:
        return jsonify({"error": "ArbitrageRunner not initialized."}), 500
    
    status = app.runner.get_status()
    return jsonify(status)

@app.route('/dashboard')
def dashboard_route(): # Renamed to avoid conflict with dashboard variable name
    # This route now just renders the main dashboard template.
    # The template itself will use JavaScript to fetch data from other endpoints.
    return render_template('dashboard.html', title='Arbitrage Bot Dashboard')

@app.route('/arbitrage_logs', methods=['GET'])
def arbitrage_logs_route():
    if app.runner is None:
        return jsonify({"error": "ArbitrageRunner not initialized."}), 500

    status_info = app.runner.get_status()
    log_file = status_info.get('log_file_path')
    
    if not log_file or not os.path.exists(log_file):
        return jsonify({"logs": [], "error": "Log file not found or path not available."}), 404

    try:
        # Read last N lines (e.g., 100)
        num_lines = int(request.args.get('lines', 100))
        with open(log_file, 'r', encoding='utf-8') as f:
            # Use deque for efficient "tail" functionality
            log_lines = list(deque(f, num_lines)) 
        return jsonify({"logs": log_lines})
    except Exception as e:
        return jsonify({"logs": [], "error": f"Error reading log file: {str(e)}"}), 500

@app.route('/trade_history', methods=['GET'])
def trade_history_route():
    if app.runner is None:
        return jsonify({"error": "ArbitrageRunner not initialized."}), 500

    status_info = app.runner.get_status()
    history_file = status_info.get('trade_history_file')

    if not history_file or not os.path.exists(history_file):
        return jsonify({"history": [], "error": "Trade history file not found or path not available."}), 404
    
    history_entries = []
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    history_entries.append(entry)
                except json.JSONDecodeError:
                    # Log this or handle malformed lines if necessary
                    app.logger.warning(f"Skipping malformed JSON line in trade history: {line.strip()}")
        # Optionally, sort by timestamp descending if entries are not always appended chronologically
        # For now, assume they are chronological. Return last N entries if requested.
        num_entries = int(request.args.get('entries', 100)) # Get last 100 by default
        return jsonify({"history": history_entries[-num_entries:]}) # Return last N
    except Exception as e:
        return jsonify({"history": [], "error": f"Error reading trade history file: {str(e)}"}), 500
