import requests
from lxml import html
import re
from requests import Session
import json
import threading
import datetime
import pytz # Keep for opp_and_solution_txt if that's still used elsewhere


def get_withdrawal_fees(exchange_instance, trading_size=1000): # Modified to accept instance
    '''
    function to get the withdrawal fees of each exchanges on website https://withdrawalfees.com/
    will also calculate the withdrawal fee percentage based on an approximate trading size
    :param exchange_instance: CCXT exchange instance (though this function uses exchange.id for URL)
    '''
    # This function seems to scrape a website. This is fragile.
    # For a robust system, using exchange.fetchDepositWithdrawFees(code) or similar CCXT methods is preferred if available.
    # However, sticking to the original structure for now.
    
    # Ensure exchange_instance has an 'id' attribute
    if not hasattr(exchange_instance, 'id'):
        print(f"ERROR: Exchange instance provided to get_withdrawal_fees has no 'id' attribute.")
        return {}
    exchange_id = exchange_instance.id

    withdrawal_fee = {}
    # Using a try-except block for robustness as website scraping can easily fail
    try:
        # print(f"Fetching withdrawal fees for {exchange_id} from withdrawalfees.com...")
        response = requests.get(f'https://withdrawalfees.com/exchanges/{exchange_id}', timeout=10) # Added timeout
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        
        tree = html.fromstring(response.content)

        for ele in tree.xpath('//tbody//tr'):
            try:
                coin_name_elements = ele.xpath('.//div[@class="symbol"]/text()')
                usd_fee_elements = ele.xpath('.//td[@class="withdrawalFee"]//div[@class="usd"]/text()')
                coin_fee_elements = ele.xpath('.//td[@class="withdrawalFee"]//div[@class="fee"]/text()')

                if not coin_name_elements: continue # Skip row if no symbol found

                coin_name = coin_name_elements[0].strip()
                
                usd_fee_text = '0' # Default to 0 if not found or FREE
                if usd_fee_elements and usd_fee_elements[0].strip().upper() != 'FREE':
                    usd_fee_match = re.findall(r'[0-9\.]+', usd_fee_elements[0])
                    if usd_fee_match:
                        usd_fee_text = usd_fee_match[0]
                
                coin_fee_text = '0'
                if coin_fee_elements and coin_fee_elements[0].strip().upper() != 'FREE': # Check if coin_fee_elements is not empty
                    coin_fee_match = re.findall(r'[0-9\.]+', coin_fee_elements[0])
                    if coin_fee_match:
                        coin_fee_text = coin_fee_match[0]
                elif usd_fee_text == '0': # If USD fee is FREE (or 0), coin fee is also 0
                     coin_fee_text = '0'


                usd_fee = float(usd_fee_text)
                coin_fee = float(coin_fee_text)

                withdrawal_fee[coin_name] = {
                    'usd_fee': usd_fee,
                    'usd_rate': usd_fee / trading_size if trading_size else 0, # Avoid division by zero
                    'coin_fee': coin_fee
                }
            except Exception as e:
                # print(f"Warning: Could not parse a row for {exchange_id} on withdrawalfees.com: {e}")
                continue # Skip this row
        
        # if not withdrawal_fee:
            # print(f"Warning: No withdrawal fees found or parsed for {exchange_id} from withdrawalfees.com.")
        return withdrawal_fee

    except requests.exceptions.RequestException as e:
        # print(f"ERROR: Could not connect to or fetch data from withdrawalfees.com for {exchange_id}: {e}")
        # Return empty dict or previously cached data if available and appropriate
        return {} # Fail gracefully for this exchange
    except Exception as e:
        # print(f"ERROR: An unexpected error occurred in get_withdrawal_fees for {exchange_id}: {e}")
        return {}


# MODIFIED SIGNATURE: Added api_key parameter
def get_crypto_prices(api_key, coin_symbols_list, convert='USD'):
    '''Fetch crypto currencies price from coin market cap api
    :param api_key: CoinMarketCap API Key string.
    :param coin_symbols_list: A list of coin symbols (e.g., ['BTC', 'ETH']).
    :param convert: The fiat currency to convert prices to (default: 'USD').
    :return: Dictionary of prices { 'SYMBOL': {'price': price_val, 'cmc_rank': rank_val} } or empty if error.
    '''
    if not api_key:
        print("ERROR: CoinMarketCap API key not provided to get_crypto_prices. Cannot fetch prices.")
        return {}
    
    if not coin_symbols_list:
        # print("INFO: No coin symbols provided to get_crypto_prices. Returning empty price data.")
        return {}

    # Filter out any non-alphabetic symbols to prevent API errors, ensure uppercase
    # CMC API usually expects uppercase symbols.
    valid_coin_symbols = list(set([str(s).upper() for s in coin_symbols_list if isinstance(s, str) and s.isalpha() and len(s) < 20]))
    if not valid_coin_symbols:
        # print("WARNING: No valid alphabetic coin symbols left after filtering in get_crypto_prices.")
        return {}

    output = {}
    # Use CoinMarketCap API v1 as per original, but v2 or v3 might be more current if issues arise.
    # url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest' # Original
    url = 'https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest' # Using v2 as it's often more flexible

    parameters = {
        'symbol': ','.join(valid_coin_symbols), # Comma-separated string of symbols
        'convert': convert.upper()
    }
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': api_key, # USE THE PASSED API KEY
    }

    try:
        session = Session() # Using a session is good practice
        session.headers.update(headers)
        response = session.get(url, params=parameters, timeout=10) # Added timeout
        response.raise_for_status()  # This will raise an HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        # Process the data based on observed CMC API structure (v1 or v2)
        if 'data' in data and isinstance(data['data'], dict):
            for symbol, crypto_data in data['data'].items():
                if isinstance(crypto_data, list): # some API versions return a list if only one symbol is queried
                    if not crypto_data: continue
                    crypto_data = crypto_data[0] # take the first element

                if isinstance(crypto_data, dict) and 'quote' in crypto_data and convert.upper() in crypto_data['quote']:
                    quote_data = crypto_data['quote'][convert.upper()]
                    if 'price' in quote_data:
                        output[symbol.upper()] = { # Store with uppercase symbol for consistency
                            'price': quote_data['price'],
                            'cmc_rank': crypto_data.get('cmc_rank', crypto_data.get('id')) # Use rank or ID as fallback
                        }
                    else:
                        # print(f"Warning: Price not found for {symbol} in {convert} quote from CMC.")
                        pass
                else:
                    # print(f"Warning: Quote data for {symbol} in {convert} not found or malformed in CMC response.")
                    pass
        else:
            error_message = "Unknown error"
            if 'status' in data and isinstance(data['status'], dict):
                error_message = data['status'].get('error_message', 'No specific error message from API.')
            # print(f"ERROR: 'data' field missing or malformed in CoinMarketCap API response. Message: {error_message}")


    except requests.exceptions.HTTPError as http_err:
        # print(f"ERROR: HTTP error fetching prices from CoinMarketCap for symbols {valid_coin_symbols}: {http_err}")
        # print(f"Response content: {response.text[:500] if response else 'No response'}") # Log part of response
        pass # Fail silently for now, returning whatever output has been populated (likely empty)
    except requests.exceptions.RequestException as e:
        # print(f"ERROR: Request exception fetching prices from CoinMarketCap: {e}")
        pass
    except json.JSONDecodeError as e:
        # print(f"ERROR: Failed to decode JSON response from CoinMarketCap: {e}")
        pass
    except Exception as e: # Catch any other unexpected error
        # print(f"ERROR: An unexpected error occurred in get_crypto_prices: {e}")
        # traceback.print_exc() # For debugging
        pass

    if not output and valid_coin_symbols: # If still no prices after trying
        # print(f"WARNING: No prices were successfully fetched from CoinMarketCap for symbols: {valid_coin_symbols}")
        pass
        
    return output


# --- Multi-threading utilities ---
# These seem generic and don't directly involve API keys or hardcoded fees.
# Assuming they are used by other parts of the 'crypto' library or potentially by ArbitrageRunner logic.
# No changes seem needed here based on the current subtask's focus.

def eachThread(func, num, partList, localVar, outputList):
    '''A helper function for each thread.'''
    output = ''
    localVar.num = num
    localVar.partList = partList
    localVar.output = output
    for i in range(len(num)):
        try:
            output = func(partList[i])
            outputList.append((num[i], output))
        except:
            # It's generally better to log the exception here or pass a specific placeholder
            # print(f"Exception in thread for item {partList[i]}: {traceback.format_exc()}")
            outputList.append((num[i], None)) # Indicate failure for this item


def multiThread(func, List, threadNum):
    '''A multi threading decorator.
       func: the function to be implemented in multi-threaded way.
       List: the input list.
       threadNum: the number of threads used, can be adjusted for different tasks.
    '''
    if not List: return [] # Handle empty list input
    if threadNum <= 0 : threadNum = 1 # Ensure at least one thread

    List = list(List)
    localVar = threading.local()
    outputList = []
    threads = [] # Keep track of thread objects
    for i in range(threadNum):
        num = range(i, len(List), threadNum)
        partList = [List[j] for j in num]
        if not partList: continue # Skip creating thread if no items for it

        t = threading.Thread(target=eachThread, args=(func, num, partList, localVar, outputList))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    
    # Sort results by original index to maintain order
    outputList = sorted(outputList, key=lambda x: x[0])
    # Extract only the processed items (results of func)
    final_results = [x[1] for x in outputList]

    return final_results


def killable_eachThread(func, num, partList, localVar, outputList, event):
    '''A helper function for each thread'''
    # This function's structure for 'output' and 'localVar' seems unusual for typical threading.
    # It's assigning to localVar.output but this isn't directly used to return values from 'func'.
    # The 'outputList.append' is what actually collects results.
    # localVar seems more for thread-local storage if 'func' needs it, not for result passing here.
    
    # localVar.num = num # Not standard, num is specific to this thread's items
    # localVar.partList = partList # Not standard
    
    for i_local, original_index in enumerate(num): # Iterate using local index and original index
        if event.is_set(): # Check if stop event is set before processing each item
            # print(f"Thread stopping early due to event for item index {original_index}.")
            outputList.append((original_index, None)) # Indicate not processed
            continue
        try:
            item_to_process = partList[i_local]
            output_item = func(item_to_process, event) # Pass event to func
            outputList.append((original_index, output_item))
        except Exception as e:
            # print(f"Exception in killable_thread for item {item_to_process} (index {original_index}): {e}")
            outputList.append((original_index, None)) # Indicate failure
        if event.is_set(): # Check again after func call in case it set the event
            # print(f"Thread stopping after func call due to event for item index {original_index}.")
            break # Exit loop for this thread


def killable_multiThread(func, List, threadNum):
    '''A multi threading decorator that provides the function when one thread stops, it kills all the other threads
       func: the function to be implemented in multi-threaded way, must accept 'event' as an argument.
       List: the input list.
       threadNum: the number of threads used, can be adjusted for different tasks.
    '''
    if not List: return []
    if threadNum <= 0 : threadNum = 1

    event = threading.Event() # Shared event to signal all threads
    List = list(List)
    localVar = threading.local() # For any thread-local storage 'func' might need (not for results)
    outputList = [] # Shared list to collect results (needs to be thread-safe or carefully managed)
    threads = []

    for i in range(threadNum):
        num_indices_for_thread = range(i, len(List), threadNum) # Original indices this thread handles
        partList_for_thread = [List[j] for j in num_indices_for_thread]
        if not partList_for_thread: continue

        # Pass num_indices_for_thread to map results back correctly
        t = threading.Thread(target=killable_eachThread, args=(func, num_indices_for_thread, partList_for_thread, localVar, outputList, event))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join() # Wait for all threads to complete (or stop early if event is set)
    
    outputList = sorted(outputList, key=lambda x: x[0])
    final_results = [x[1] for x in outputList]

    return final_results


# --- Output formatting and saving functions ---
# These also seem generic and not directly related to hardcoded configs.
# Assuming they are used elsewhere or by ArbitrageRunner.

def opp_and_solution_txt(path_optimizer, amt_optimizer):
    '''output the print content from path_optimizer and amt_optimizer'''
    tz = pytz.timezone('Asia/Singapore') # Consider making timezone configurable if app is used globally
    current_time_str = str(datetime.datetime.now().astimezone(tz))
    
    # Ensure path_optimizer has print_content attribute
    print1 = getattr(path_optimizer, 'print_content', "Path Optimizer did not generate content.")
    
    print2 = ""
    # Check if path_optimizer exists, has have_opportunity method, and opportunity exists
    if path_optimizer and hasattr(path_optimizer, 'have_opportunity') and path_optimizer.have_opportunity():
        if amt_optimizer and hasattr(amt_optimizer, 'print_content'):
            print2 = amt_optimizer.print_content
        else:
            print2 = "Amount Optimizer did not generate content or not available."
    
    output = '-------------------------------\n{}\n{}\n{}\n\n'.format(current_time_str, print1, print2)
    return output


def save_to_file(output_content, filename='record.txt'): # Allow filename to be passed
    '''save the print content to a specified file'''
    try:
        with open(filename, 'a') as f: # Open in append mode 'a'
            f.write(output_content)
    except Exception as e:
        print(f"Error saving to file {filename}: {e}")


def save_record(path_optimizer, amt_optimizer, filename='record.txt'): # Allow filename
    output = opp_and_solution_txt(path_optimizer, amt_optimizer)
    save_to_file(output, filename)

```
