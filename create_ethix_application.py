import os
import time
import pickle
import requests
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from IPython.display import display, clear_output
from io import BytesIO
from PIL import Image
from selenium.common.exceptions import TimeoutException

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ethix_application.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def initialize_driver():
    logger.debug("Initializing web driver")
    try:
        # Try to use google_colab_selenium first
        import google_colab_selenium as gs
        driver = gs.Chrome()
        logger.info("Using google_colab_selenium driver")
    except (ImportError, AssertionError):
        # If not in Colab, use regular selenium
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        driver = webdriver.Chrome(options=chrome_options)
        logger.info("Using regular selenium driver")
    
    driver.set_window_size(1920, 1080)
    return driver

def handle_bankid_login(driver):
    logger.debug("Starting BankID login process")
    driver.get('https://www.etikprovningsansokan.se/epm/login')
    logger.debug(f"Current URL: {driver.current_url}")
    
    # Find and click the "Mobilt BankID" button
    bankid_button = driver.find_element(By.ID, "bankid_remote_btn")
    bankid_button.click()
    logger.debug("Clicked BankID button")
    
    # Wait for the QR code canvas to appear
    wait = WebDriverWait(driver, 10)
    qr_code_element = wait.until(EC.presence_of_element_located((By.ID, "bankid_qr_code_div")))
    
    qr_displayed = False
    while True:
        try:
            canvas = driver.find_element(By.ID, "bankid_qr_code_div")
            png = canvas.screenshot_as_png
            clear_output(wait=True)
            display(Image.open(BytesIO(png)))
            qr_displayed = True
            time.sleep(0.5)
        except Exception as e:
            if "no such element" in str(e) and qr_displayed:
                clear_output(wait=True)
                logger.info("Sign in completed successfully")
                return True
            else:
                logger.error(f"Login error: {e}")
                return False

def navigate_to_form(driver):
    logger.debug("Navigating to form")
    wait = WebDriverWait(driver, 10)
    
    # Navigate to applications page
    driver.get('https://www.etikprovningsansokan.se/epm/apps')
    logger.debug(f"Current URL: {driver.current_url}")
    
    # Wait for and click the "Grundansökan" link
    grundansokan_link = wait.until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "Grundansökan")))
    
    # Extract the form number
    form_number = grundansokan_link.get_attribute('href').split('form=')[1]
    with open('form_number.txt', 'w') as f:
        f.write(form_number)
    logger.info(f"Form number extracted: {form_number}")
    
    # Click the link
    grundansokan_link.click()
    logger.debug("Clicked Grundansökan link")
    
    # Wait for form page to load
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="submit"][name="set_cond"]')))
    logger.debug(f"Form page loaded: {driver.current_url}")
    
    return form_number

def fill_form(driver, field_values):
    logger.debug("Starting to fill form")
    wait = WebDriverWait(driver, 10)
    
    for field_id, value in field_values.items():
        logger.debug(f"Processing field {field_id} with value {value}")
        checkbox = wait.until(EC.presence_of_element_located((By.ID, field_id)))
        is_checked = checkbox.is_selected()
        
        if (value == 1 and not is_checked) or (value == 0 and is_checked):
            checkbox.click()
            logger.debug(f"Clicked checkbox {field_id}")
    
    # Submit form
    submit_button = wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, 'input[type="submit"][name="set_cond"][value="Fortsätt"]')))
    submit_button.click()
    logger.debug("Clicked submit button")

    
    
    # Wait for URL change and extract p_id with timeout handling
    try:
        wait.until(lambda driver: 'p_id=' in driver.current_url)
        current_url = driver.current_url
        logger.debug(f"New URL after submit: {current_url}")
        p_id = current_url.split('p_id=')[1].split('&')[0]
    except TimeoutException:
        # If URL doesn't change, try to find p_id in the page source or another element
        logger.warning("URL did not change as expected, attempting alternative p_id extraction")
        try:
            # Look for hidden input with p_id or another reliable element containing p_id
            p_id_element = wait.until(EC.presence_of_element_located((By.NAME, "p_id")))
            p_id = p_id_element.get_attribute("value")
            logger.debug(f"Found p_id through alternative method: {p_id}")
        except Exception as e:
            logger.error(f"Failed to extract p_id: {str(e)}")
            raise
    
    # Save p_id
    with open('p_id.txt', 'w') as f:
        f.write(p_id)
    logger.info(f"P_ID extracted: {p_id}")
    
    return p_id

def send_form_data(cookies, form_number, p_id, form_data=None):
    logger.debug("Preparing to send form data")
    url = 'https://www.etikprovningsansokan.se/epm/ansokan/edit'
    
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://www.etikprovningsansokan.se',
        'Referer': 'https://www.etikprovningsansokan.se/epm/ansokan/edit',
    }
    
    cookies_dict = {cookie['name']: cookie['value'] for cookie in cookies}
    logger.debug(f"Cookies being used: {cookies_dict}")
    
    # Base data that's always needed
    data = {
        'ckeditor': '1',
        'return_path': '/ansokan/new',
        'f_id': form_number,
        'p_id': p_id,
        'id': '0',
        'module': 'ansokan',
        'save_form': 'Spara'
    }
    
    # Update with any additional form data
    if form_data:
        data.update(form_data)
    logger.debug(f"Form data being sent: {data}")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, cookies=cookies_dict, data=data)
            response.raise_for_status()  # Raise exception for non-200 status codes
            logger.debug(f"Response status code: {response.status_code}")
            logger.debug(f"Response content: {response.text[:500]}...")  # First 500 chars of response
            return response.status_code
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:  # Last attempt
                logger.error(f"Failed to submit form after {max_retries} attempts: {str(e)}")
                raise
            logger.warning(f"Form submission attempt {attempt + 1} failed, retrying...")
            time.sleep(2 ** attempt)  # Exponential backoff

def process_responses(responses, field_mapping):
    """Convert AI responses to form field values"""
    logger.debug("Processing AI responses")
    logger.debug(f"Input responses: {responses}")
    
    field_values = {}  # For checkboxes (preform)
    form_data = {}     # For main form fields
    
    for response_key, response_value in responses.items():
        # Find matching field in mapping
        matching_field = None
        field_id = None
        
        for f_id, field_info in field_mapping.items():
            if field_info.get('question_id') == response_key:
                matching_field = field_info
                field_id = f_id
                logger.debug(f"\nProcessing response for question {response_key}")
                logger.debug(f"Found matching field: {field_id}")
                logger.debug(f"Field info: {field_info}")
                break
        
        if not matching_field:
            logger.warning(f"No matching field found for response {response_key}")
            continue
            
        # Process based on field type
        if matching_field['field_type'] == 'ftype_checkbox':
            # Convert boolean/text response to 1/0
            value = 1 if str(response_value).lower() in ['yes', 'true', '1', 'ja'] else 0
            field_values[field_id] = value
            logger.debug(f"Added checkbox value: {field_id} = {value}")
            
        elif matching_field['field_type'] == 'ftype_7':  # Radio buttons
            form_var = matching_field.get('form_variable')
            if not form_var:
                logger.warning(f"No form variable found for field {field_id}")
                continue
            
            # Handle numeric responses directly
            try:
                value = int(response_value)
                # Verify the value exists in options
                valid_values = [int(opt['value']) for opt in matching_field.get('options', [])]
                if value in valid_values:
                    if form_var.endswith('_int'):
                        form_data[form_var] = value
                    else:
                        form_data[form_var] = str(value)
                    logger.debug(f"Added radio value: {form_var} = {value}")
                else:
                    logger.warning(f"Invalid radio value {value} for field {field_id}. Valid values: {valid_values}")
            except (ValueError, TypeError):
                # If not numeric, try to match by text
                found_match = False
                for option in matching_field.get('options', []):
                    if option['text'].lower() == str(response_value).lower():
                        value = int(option['value']) if form_var.endswith('_int') else option['value']
                        form_data[form_var] = value
                        found_match = True
                        logger.debug(f"Added radio value by text match: {form_var} = {value}")
                        break
                
                if not found_match:
                    logger.warning(f"No matching option found for response {response_value} in field {field_id}")
                
        else:
            # Text fields
            form_var = matching_field.get('form_variable')
            if not form_var:
                logger.warning(f"No form variable found for field {field_id}")
                continue
                
            # Cast to int if form variable ends with _int
            if form_var.endswith('_int'):
                try:
                    form_data[form_var] = int(response_value)
                    logger.debug(f"Added int value: {form_var} = {form_data[form_var]}")
                except (ValueError, TypeError):
                    logger.warning(f"Could not convert {response_value} to int for {form_var}")
                    continue
            else:
                form_data[form_var] = str(response_value)
                logger.debug(f"Added string value: {form_var} = {form_data[form_var]}")
    
    logger.debug(f"\nFinal results:")
    logger.debug(f"field_values: {field_values}")
    logger.debug(f"form_data: {form_data}")
    return field_values, form_data

def main(field_values=None, form_data=None):
    """
    Main function that accepts either:
    - field_values + form_data: for direct form submission
    """
    logger.info("Starting application process")
    
    driver = initialize_driver()
    try:
        if handle_bankid_login(driver):
            form_number = navigate_to_form(driver)
            
            if field_values:
                p_id = fill_form(driver, field_values)
                
                # Save cookies
                cookies = driver.get_cookies()
                with open('cookies.pkl', 'wb') as file:
                    pickle.dump(cookies, file)
                logger.debug(f"Saved cookies: {cookies}")
                
                if form_data:
                    status_code = send_form_data(cookies, form_number, p_id, form_data)
                    logger.info(f"Form submission status code: {status_code}")
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}", exc_info=True)
    finally:
        driver.quit()
        logger.info("Driver closed")

# Example usage:
if __name__ == "__main__":
    # Complete field mapping for both checkbox and text fields
    example_field_mapping = {
        'dsd_8384': {
            'question_id': 'science',
            'field_type': 'ftype_checkbox'
        },
        'dsd_8385': {
            'question_id': 'tech',
            'field_type': 'ftype_checkbox'
        },
        'a_1316982_text': {
            'question_id': 'title',
            'field_type': 'ftype_text'
        }
    }
    
    # Research area responses (for checkboxes/fill_form)
    example_responses = {
        'science': 'yes',
        'tech': 'no'
    }
    
    # Form data responses (for text fields/send_form_data)
    example_form_data = {
        'title': 'test'
    }
    
    # Process each separately using the same mapping
    field_values, _ = process_responses(example_responses, example_field_mapping)
    _, form_data = process_responses(example_form_data, example_field_mapping)
    
    main(field_values=field_values, form_data=form_data)