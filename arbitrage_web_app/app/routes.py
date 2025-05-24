from flask import current_app as app, jsonify, request, render_template, flash, redirect, url_for
from .forms import AppConfigForm # Assuming forms.py is in the same directory (app)
from .models import ArbitrageRecord # Import the ArbitrageRecord model
import json
import yaml # For prettier YAML output
import os 
from collections import deque # For reading last N lines efficiently

@app.route('/')
def home():
    # Redirect to the new comprehensive dashboard
    return redirect(url_for('dashboard_route'))


@app.route('/start_arbitrage', methods=['POST'])
def start_arbitrage_route():
    if app.runner is None:
        return jsonify({"error": "ArbitrageRunner not initialized. Check server logs for details on import or initialization errors."}), 500
    
    current_status_info = app.runner.get_status()
    if current_status_info.get('status') == "running" or current_status_info.get('process_alive'):
        return jsonify({"error": "Arbitrage process already running or starting.", "status": current_status_info}), 400
    
    parameter_message = "default"
    if request.is_json:
        params_override = request.get_json()
        if params_override and isinstance(params_override, dict):
            try:
                # Assuming app.runner.set_optimizer_parameters exists and handles validation/logging
                app.runner.set_optimizer_parameters(params_override) 
                parameter_message = "custom"
                app.logger.info(f"Custom optimizer parameters applied for this run: {params_override}")
            except Exception as e_set_params:
                app.logger.error(f"Error setting optimizer parameters: {e_set_params}")
                return jsonify({"error": f"Error applying optimizer parameters: {str(e_set_params)}", "status": app.runner.get_status()}), 400
        elif params_override is not None: 
             app.logger.warning("Received non-dict or empty JSON payload for optimizer params. Using defaults.")
    
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
def dashboard_route(): 
    defi_ready = False
    defi_message = "DeFi Bot Manager not initialized or not ready."
    if hasattr(app, 'defi_runner') and app.defi_runner:
        is_ready_flag, msg = app.defi_runner.is_ready()
        if is_ready_flag:
            defi_ready = True
            defi_message = msg # Usually "Ready"
        else:
            defi_message = f"DeFi Bot not ready: {msg}"
            app.logger.warning(f"DeFi runner not ready for dashboard: {msg}")
    else:
        app.logger.warning("DeFi runner (app.defi_runner) not found on app context for dashboard.")

    return render_template('dashboard.html', title='Arbitrage Bot Dashboard', defi_ready=defi_ready, defi_message=defi_message)

@app.route('/arbitrage_logs', methods=['GET'])
def arbitrage_logs_route():
    if app.runner is None:
        return jsonify({"error": "ArbitrageRunner not initialized."}), 500

    status_info = app.runner.get_status()
    log_file = status_info.get('log_file_path')
    
    if not log_file or not os.path.exists(log_file):
        return jsonify({"logs": [], "error": "Log file not found or path not available."}), 404

    try:
        num_lines = int(request.args.get('lines', 100))
        with open(log_file, 'r', encoding='utf-8') as f:
            log_lines = list(deque(f, num_lines)) 
        return jsonify({"logs": log_lines})
    except Exception as e:
        return jsonify({"logs": [], "error": f"Error reading log file: {str(e)}"}), 500

@app.route('/trade_history', methods=['GET'])
def trade_history_route():
    # No longer reads from file, now queries DB
    num_entries = int(request.args.get('entries', 100))
    try:
        records = ArbitrageRecord.query.order_by(ArbitrageRecord.timestamp.desc()).limit(num_entries).all()
        history_entries = [record.to_dict() for record in records]
        return jsonify({"history": history_entries})
    except Exception as e:
        app.logger.error(f"Error querying trade history from database: {e}")
        return jsonify({"history": [], "error": f"Error querying trade history from database: {str(e)}"}), 500


@app.route('/configure', methods=['GET', 'POST'])
def configure_route():
    form = AppConfigForm()
    env_vars_output = ""
    yaml_output = ""
    json_parse_errors = {}

    if request.method == 'GET':
        if not form.exchanges.entries:
            form.exchanges.append_entry() 

    if form.validate_on_submit():
        cmc_api_key = form.cmc_api_key.data
        
        trading_fees_dict = {}
        try:
            loaded_fees = json.loads(form.trading_fees_json.data)
            if isinstance(loaded_fees, dict):
                trading_fees_dict = loaded_fees
            else:
                json_parse_errors['trading_fees_json'] = "Trading fees must be a valid JSON object (dictionary)."
        except json.JSONDecodeError as e:
            json_parse_errors['trading_fees_json'] = f"Invalid JSON for Trading Fees: {e}"

        exchange_configs_dict = {}
        for i, exchange_form_field in enumerate(form.exchanges.entries):
            exchange_data = exchange_form_field.form.data
            ex_name = exchange_data.get('exchange_name')
            if not ex_name: continue

            current_ex_config = {
                'apiKey': exchange_data.get('apiKey'),
                'secret': exchange_data.get('secret'),
            }
            if exchange_data.get('password'):
                current_ex_config['password'] = exchange_data.get('password')
            
            other_params_json_str = exchange_data.get('other_params_json', '{}')
            try:
                if other_params_json_str and other_params_json_str.strip():
                    other_params = json.loads(other_params_json_str)
                    if isinstance(other_params, dict):
                        current_ex_config.update(other_params)
                    else:
                        json_parse_errors[f'exchanges-{i}-other_params_json'] = "Other Parameters must be a valid JSON object."
            except json.JSONDecodeError as e:
                json_parse_errors[f'exchanges-{i}-other_params_json'] = f"Invalid JSON for Other Parameters: {e}"
            exchange_configs_dict[ex_name] = current_ex_config
        
        # DeFi settings
        polygon_rpc_url = form.polygon_rpc_url.data
        biconomy_api_key = form.biconomy_api_key.data
        private_key = form.private_key.data 
        polygonscan_api_key = form.polygonscan_api_key.data
        flash_loan_contract_address = form.flash_loan_contract_address.data
        gasless_contract_address = form.gasless_contract_address.data


        if not json_parse_errors:
            flash('Configuration data processed. Review output below to apply manually.', 'success')
            env_vars_list = []
            
            if cmc_api_key: env_vars_list.append(f"export CMC_API_KEY='{cmc_api_key}'")
            
            # DeFi Core
            if polygon_rpc_url: env_vars_list.append(f"export POLYGON_RPC_URL='{polygon_rpc_url}'")
            if biconomy_api_key: env_vars_list.append(f"export BICONOMY_API_KEY='{biconomy_api_key}'")
            if private_key:
                env_vars_list.append(f"# SECURITY WARNING: The following PRIVATE_KEY is highly sensitive. Store and use securely.")
                env_vars_list.append(f"export PRIVATE_KEY='{private_key}'")
            if polygonscan_api_key: env_vars_list.append(f"export POLYGONSCAN_API_KEY='{polygonscan_api_key}'")
            
            # DeFi Contract Addresses
            if flash_loan_contract_address: env_vars_list.append(f"export FLASH_LOAN_CONTRACT_ADDRESS='{flash_loan_contract_address}'")
            if gasless_contract_address: env_vars_list.append(f"export GASLESS_CONTRACT_ADDRESS='{gasless_contract_address}'")


            if exchange_configs_dict:
                env_vars_list.append(f"export EXCHANGE_CONFIGS='{json.dumps(exchange_configs_dict)}'")
            if trading_fees_dict:
                env_vars_list.append(f"export TRADING_FEES_CONFIG='{json.dumps(trading_fees_dict)}'")
            
            env_vars_output = "\n".join(env_vars_list)

            conceptual_config_file_dict = {
                'cmc_api_key': cmc_api_key or "[Not Set]",
                'trading_fees': trading_fees_dict,
                'exchanges': exchange_configs_dict,
            }
            final_defi_yaml = {}
            if polygon_rpc_url: final_defi_yaml['polygon_rpc_url'] = polygon_rpc_url
            if biconomy_api_key: final_defi_yaml['biconomy_api_key'] = biconomy_api_key
            if private_key: final_defi_yaml['private_key'] = "[SENSITIVE] Set via securely managed ENV_VAR"
            if polygonscan_api_key: final_defi_yaml['polygonscan_api_key'] = polygonscan_api_key
            if flash_loan_contract_address: final_defi_yaml['flash_loan_contract_address'] = flash_loan_contract_address
            if gasless_contract_address: final_defi_yaml['gasless_contract_address'] = gasless_contract_address
            
            if final_defi_yaml: 
                conceptual_config_file_dict['defi_settings'] = final_defi_yaml
            
            try:
                yaml_output = yaml.dump(conceptual_config_file_dict, sort_keys=False, indent=2, default_flow_style=False)
            except Exception as e:
                yaml_output = f"Error generating YAML: {e}"
        else:
            for field, error_msg in json_parse_errors.items():
                 flash(f"Error in field '{field}': {error_msg}", 'danger')
            flash('Configuration processing failed due to JSON errors. Please correct and resubmit.', 'danger')

    elif request.method == 'POST': 
        flash('Form validation failed. Please check the errors below.', 'danger')

    return render_template('configure.html', title='Configure Arbitrage Bot', form=form, 
                           env_vars_output=env_vars_output, yaml_output=yaml_output,
                           json_errors=json_parse_errors)

# --- DeFi Endpoints ---
@app.route('/execute_flash_loan', methods=['POST'])
def execute_flash_loan_route():
    if not hasattr(app, 'defi_runner') or app.defi_runner is None:
        return jsonify({"success": False, "error": "DeFiBotManager not initialized."}), 503
    
    ready, msg = app.defi_runner.is_ready()
    if not ready:
        return jsonify({"success": False, "error": f"DeFiBotManager not ready: {msg}"}), 503

    opportunity_data = None
    if hasattr(app, 'runner') and app.runner:
        runner_status = app.runner.get_status()
        opportunity_data = runner_status.get('last_opportunity')
        if opportunity_data:
             app.logger.info(f"Attempting flash loan with last CEX opportunity: {opportunity_data.get('p_value')}")
        else:
            app.logger.info("Attempting flash loan without specific prior CEX opportunity data.")
            
    result = app.defi_runner.execute_flash_loan_arbitrage(opportunity_data=opportunity_data)
    return jsonify(result)

@app.route('/execute_gasless_transaction', methods=['POST'])
def execute_gasless_transaction_route():
    if not hasattr(app, 'defi_runner') or app.defi_runner is None:
        return jsonify({"success": False, "error": "DeFiBotManager not initialized."}), 503

    ready, msg = app.defi_runner.is_ready()
    if not ready:
        return jsonify({"success": False, "error": f"DeFiBotManager not ready: {msg}"}), 503

    opportunity_data = None
    if hasattr(app, 'runner') and app.runner:
        runner_status = app.runner.get_status()
        opportunity_data = runner_status.get('last_opportunity')
        if opportunity_data:
            app.logger.info(f"Attempting gasless transaction with last CEX opportunity: {opportunity_data.get('p_value')}")
        else:
            app.logger.info("Attempting gasless transaction without specific prior CEX opportunity data.")

    result = app.defi_runner.execute_gasless_arbitrage(opportunity_data=opportunity_data)
    return jsonify(result)

# --- Smart Contract Info Page ---
@app.route('/smart_contracts_info')
def smart_contracts_info_route():
    flash_loan_addr = app.config.get('FLASH_LOAN_CONTRACT_ADDRESS', "Not configured")
    gasless_addr = app.config.get('GASLESS_CONTRACT_ADDRESS', "Not configured")
    
    contracts_info = [
        {
            "name": "FlashLoanArbitrage.sol (Conceptual)",
            "description": "This smart contract would be designed to execute arbitrage opportunities using flash loans on a DeFi protocol (e.g., on Polygon). It would atomically borrow assets, perform a sequence of swaps across DEXes, and repay the loan with a fee, all within one transaction. The profit is realized if the swaps yield more than the borrowed amount plus fees.",
            "address": flash_loan_addr,
            "typical_network": "Polygon (or compatible EVM testnet)"
        },
        {
            "name": "GaslessTransactionRelayer.sol (Conceptual - could be part of a system like Biconomy)",
            "description": "This contract (or system) would facilitate gas-less transactions. The bot submits a transaction meta-data, which is then relayed by a third party who pays the gas fees. This is useful for automating DeFi interactions without the bot's primary wallet needing to manage gas tokens directly for every action. The relayer might be compensated through a fee or from a portion of the arbitrage profit.",
            "address": gasless_addr,
            "typical_network": "Polygon (or compatible EVM testnet)"
        }
    ]
    
    deployment_script_info = {
        "script_name": "crypto/deploy_contracts.py (Hypothetical)",
        "recommendation": "This script would be used to deploy the arbitrage-related smart contracts to the chosen blockchain network. It should be run from a secure development environment with proper access controls.",
        "requirements": "Deployment typically requires a private key with sufficient native currency (e.g., MATIC for Polygon) for gas fees, a connection to a blockchain node (RPC URL), and the compiled contract artifacts. Tools like Hardhat or Truffle are often used to manage this process.",
        "caution": "Direct contract deployment features are NOT integrated into this web UI due to the high security risks associated with handling private keys, deployment parameters, and contract bytecode through a web interface."
    }
    
    return render_template('smart_contracts_info.html', 
                           title="Smart Contract Information", 
                           contracts=contracts_info, 
                           deployment_info=deployment_script_info)
```
