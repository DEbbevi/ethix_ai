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

def main(field_values=None, form_data=None):
    logger.info("Starting application process")
    driver = initialize_driver()
    try:
        if handle_bankid_login(driver):
            form_number = navigate_to_form(driver)
            
            # Only proceed with form filling if field_values provided
            if field_values:
                p_id = fill_form(driver, field_values)
                
                # Save cookies
                cookies = driver.get_cookies()
                with open('cookies.pkl', 'wb') as file:
                    pickle.dump(cookies, file)
                logger.debug(f"Saved cookies: {cookies}")
                
                # Send form data if provided
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
    #Example usage:
    field_values = {
        'dsd_8384': 1,  # Naturvetenskap: Ja
        'dsd_8385': 0,  # Teknik: Nej
    }
    form_data = {
        'a_1316982_text': 'test',  # Example field
    }
    main(field_values, form_data)