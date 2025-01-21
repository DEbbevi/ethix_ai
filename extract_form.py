from bs4 import BeautifulSoup, NavigableString, Tag
import re
from typing import Dict, List, Optional
from dataclasses import dataclass
from mermaid_parser import parse_mermaid_flow, FlowStage, PromptGroup
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

@dataclass
class FormField:
    id: str
    variable_name: str
    title: str
    help_text: str
    field_type: str
    char_limit: int = 0
    stage: Optional[FlowStage] = None
    prompt_group: str = ""
    options: List[Dict[str, str]] = None
    condition: str = ""

def validate_field_hierarchy(field_mapping: Dict[str, Dict]) -> List[Dict]:
    """
    Validate that all parent questions exist for numbered questions.
    For example, if question 14.4.1 exists, verify that 14.4 exists (but not 14).
    """
    # Extract all question numbers from titles
    question_numbers = set()
    numbered_fields = {}
    
    for field_id, field_info in field_mapping.items():
        # Extract question number from title (e.g., "14.4.1" from "14.4.1 Title...")
        title = field_info['title']
        if title.startswith('14'):
            logger.debug(f"\nDEBUG: Processing field {field_id}")
            logger.debug(f"Title: '{title}'")
            
        match = re.match(r'^(\d+(?:\.\d+)*)\s*(?:\[.*?\])?\s*', title)
        if match:
            number = match.group(1)
            question_numbers.add(number)
            numbered_fields[number] = field_info
    
    # Check for missing parent questions
    missing_parents = []
    
    for number in sorted(question_numbers):
        parts = number.split('.')
        if len(parts) <= 2:  # Skip validation for X.Y format (no parent needed)
            continue
            
        # Generate parent numbers, but skip the top level
        parent_numbers = []
        for i in range(2, len(parts)):
            parent_numbers.append('.'.join(parts[:i]))
        
        
        # Check if each parent exists
        for parent in parent_numbers:
            if parent not in question_numbers:
                logger.warning(f"Missing parent: {parent}")
                missing_parents.append({
                    'missing': parent,
                    'child': number,
                    'child_title': numbered_fields[number]['title']
                })
    
    return missing_parents

def extract_form_fields(html_content: str) -> List[FormField]:
    """Extract form fields and their metadata from the HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    fields = []
    
    # Find all div elements with class fieldclass
    field_divs = soup.find_all('div', class_='fieldclass')
    fields.extend(_extract_main_form_fields(field_divs))
    
    # Find all preform fields (dt elements with checkboxes)
    dt_elements = soup.find_all('dt')
    fields.extend(_extract_preform_fields(dt_elements))
    
    return fields

def _extract_preform_fields(dt_elements: List[Tag]) -> List[FormField]:
    """Extract fields from preform dt elements."""
    fields = []
    
    for dt in dt_elements:
        checkbox = dt.find('input', type='checkbox')
        if not checkbox:
            continue
            
        field_id = checkbox.get('id', '')
        if not field_id or not field_id.startswith('dsd_'):
            continue
            
        # Get title from the label's strong tag
        label = dt.find('label')
        title = label.find('strong').get_text(strip=True) if label and label.find('strong') else ""
        
        # Get help text from the following dd element
        help_text = ""
        dd = dt.find_next('dd')
        if dd:
            help_text = dd.get_text(strip=True)
        
        fields.append(FormField(
            id=field_id,
            variable_name=field_id,  # Keep the dsd_ prefix
            title=title,
            help_text=help_text,
            field_type="ftype_checkbox",
            char_limit=0,
            options=[
                {'value': '1', 'text': 'Ja'},
                {'value': '0', 'text': 'Nej'},
            ],
            condition=""
        ))
    
    return fields

def _extract_main_form_fields(field_divs: List[Tag]) -> List[FormField]:
    """Extract fields from main form field divs."""
    fields = []
    
    # Debug: Only log fields we're specifically interested in
    logger.debug("\nSearching for field 14.1.5...")
    for div in field_divs:
        field_id = div.get('id', '')
        title_tag = div.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else ""
        if '14.1.5' in title:  # Only debug field 14.1.5
            logger.debug(f"\nFound field 14.1.5:")
            logger.debug(f"ID: {field_id}")
            logger.debug(f"Title: {title}")
            logger.debug(f"Classes: {div.get('class', [])}")
            logger.debug(f"Field type class: {next((c for c in div.get('class', []) if c.startswith('ftype_')), 'None')}")
            
            # Debug the radio button extraction specifically
            inputs = div.find_all('input', type='radio')
            logger.debug(f"Number of radio options found: {len(inputs)}")
            for input_tag in inputs:
                label = input_tag.find_next('label')
                value = input_tag.get('value', '')
                text = label.get_text(strip=True) if label else ''
                logger.debug(f"Option - value: {value}, text: {text}")
    
    for div in field_divs:
        field_id = div.get('id', '')
        if not field_id:
            continue
            
        field_type = _get_field_type(div)
        condition = div.get('condition', '')
        variable_name = f"a_{field_id}"
        title = _get_title(div)
        help_text = _get_help_text(div)
        char_limit = _get_char_limit(div)
        
        # Add specific debugging for 14.1.5 options extraction
        if '14.1.5' in title:
            logger.debug(f"\nExtracting options for 14.1.5:")
            logger.debug(f"Field type detected: {field_type}")
            options = _get_field_options(div, field_type)
            logger.debug(f"Options extracted: {options}")
        else:
            options = _get_field_options(div, field_type)
        
        # Skip empty/header fields
        if not title and field_type == 'ftype_104':
            continue
            
        fields.append(FormField(
            id=field_id,
            variable_name=variable_name,
            title=title,
            help_text=help_text,
            field_type=field_type,
            char_limit=char_limit,
            options=options if options else None,
            condition=condition
        ))
        
        # Confirm field was added
        if '14.1.5' in title:
            logger.debug(f"\nField 14.1.5 added to fields list:")
            logger.debug(f"Field type: {field_type}")
            logger.debug(f"Options: {options}")
    
    return fields

def _get_field_type(div: Tag) -> str:
    """Get the field type from the div's classes."""
    classes = div.get('class', [])
    
    # Debug output for radio button fields
    if 'ftype_7' in classes:
        logger.debug(f"\nDEBUG: Found radio button field:")
        logger.debug(f"ID: {div.get('id')}")
        logger.debug(f"Title: {div.find('h1').get_text(strip=True) if div.find('h1') else ''}")
        logger.debug(f"Options: {[opt.get_text(strip=True) for opt in div.find_all('label')]}")
    
    for class_name in classes:
        if class_name.startswith('ftype_'):
            return class_name
    return ''

def _get_title(div: Tag) -> str:
    """Extract title from h1 tag."""
    title_tag = div.find('h1')
    if title_tag:
        title = title_tag.get_text(strip=True)
        # Debug output for section 14
        if title.startswith('14'):
            logger.debug(f"DEBUG: Raw title found: '{title}'")
            logger.debug(f"DEBUG: HTML of title: {title_tag}")
        return title
    return ""

def _get_help_text(div: Tag) -> str:
    """Extract help text following the title."""
    title_tag = div.find('h1')
    if not title_tag:
        return ""
        
    help_paragraphs = []
    current = title_tag.next_sibling
    while current:
        if isinstance(current, NavigableString):
            text = current.strip()
            if text:
                help_paragraphs.append(text)
        elif current.name == 'p':
            text = current.get_text(strip=True)
            if text:
                help_paragraphs.append(text)
        elif current.name == 'div' and 'forminput' in current.get('class', []):
            break
        current = current.next_sibling
    return '\n'.join(help_paragraphs)

def _get_char_limit(div: Tag) -> int:
    """Extract character limit if present."""
    char_limit_div = div.find('div', class_='char_limit')
    if char_limit_div:
        limit_text = char_limit_div.get_text()
        match = re.search(r'upp till (\d+) tecken', limit_text)
        if match:
            return int(match.group(1))
    return 0

def _get_field_options(div: Tag, field_type: str) -> List[Dict[str, str]]:
    """Extract options for fields that have them (radio, select, etc)."""
    options = []
    
    if field_type == 'ftype_7':  # Radio buttons
        # Find all radio inputs and their labels
        for input_tag in div.find_all('input', type='radio'):
            value = input_tag.get('value', '')
            # Find the label that follows this input
            label = input_tag.find_next('label')
            text = label.get_text(strip=True) if label else ''
            if value and text:
                options.append({
                    'value': value,
                    'text': text
                })
    elif field_type == 'ftype_5':  # Select dropdowns
        # ... existing select handling code ...
        pass
        
    return options

def parse_form_data(form_data: str) -> Dict[str, str]:
    """Parse the form data from the network request."""
    data = {}
    pairs = form_data.split('&')
    for pair in pairs:
        if '=' not in pair:
            continue
        key, value = pair.split('=', 1)
        if key.startswith('a_'):
            data[key] = value
    return data

def create_field_mapping(html_content: str, form_data: str, mermaid_content: str) -> Dict[str, Dict]:
    """Create a mapping between form fields and their metadata, including Mermaid structure."""
    fields = extract_form_fields(html_content)
    form_data_dict = parse_form_data(form_data)
    prompt_groups = parse_mermaid_flow(mermaid_content)
    
    # Debug extracted fields
    logger.debug("\nAll extracted fields before mapping:")
    for field in fields:
        logger.debug(f"Field ID: {field.id}, Title: {field.title}, Type: {field.field_type}")
    
    # Create reverse lookup for question IDs to their location
    question_locations = {}
    # Track all questions from Mermaid
    mermaid_questions = set()
    for group_name, prompt_group in prompt_groups.items():
        for question in prompt_group.questions:
            mermaid_questions.add(question)
            question_locations[question] = {
                "stage": prompt_group.stage,
                "prompt_group": group_name
            }
    
    mapping = {}
    unmapped_fields = []
    found_questions = set()
    
    for field in fields:
        question_match = re.match(r'^(\d+\.\d+(?:\.\d+)?)', field.title)
        if question_match:
            question_id = question_match.group(1)
            found_questions.add(question_id)
            
            # Debug mapping process for section 14
            if question_id.startswith('14'):
                logger.debug(f"\nProcessing field for mapping:")
                logger.debug(f"Question ID: {question_id}")
                logger.debug(f"Title: {field.title}")
                logger.debug(f"Variable name: {field.variable_name}")
                logger.debug(f"Field type: {field.field_type}")
                logger.debug(f"Condition: {field.condition}")
            
            # For radio button fields (ftype_7), only use _int suffix
            form_var = f"{field.variable_name}_int" if field.field_type == 'ftype_7' else f"{field.variable_name}_text"
            
            # Always include conditional radio button fields in mapping
            if field.field_type == 'ftype_7' or form_var in form_data_dict:
                location = question_locations.get(question_id, {
                    "stage": None,
                    "prompt_group": ""
                })
                
                mapping[field.variable_name] = {
                    "title": field.title,
                    "help_text": field.help_text,
                    "field_type": field.field_type,
                    "form_variable": form_var,
                    "char_limit": field.char_limit,
                    "stage": location["stage"].name if location["stage"] else "",
                    "prompt_group": location["prompt_group"],
                    "question_id": question_id,
                    "options": field.options,
                    "condition": field.condition
                }
                
                if question_id.startswith('14'):
                    logger.debug(f"Added to mapping with form variable: {form_var}")
            else:
                if question_id.startswith('14'):
                    logger.debug(f"Not added to mapping - form variable not found: {form_var}")
    
    return mapping

def load_and_create_mappings(preform_html_file: str = 'forms/preform_copy.html',
                           main_html_file: str = 'forms/form_copy.html',
                           form_data_file: str = 'forms/form_data.txt',
                           mermaid_file: str = 'forms/flow.mermaid',
                           verbose: bool = False) -> Dict[str, Dict]:
    """Load all required files and create field mappings for both preform and main form."""
    # Load the files
    with open(preform_html_file, 'r', encoding='utf-8') as f:
        preform_html_content = f.read()
    
    with open(main_html_file, 'r', encoding='utf-8') as f:
        main_html_content = f.read()
    
    with open(form_data_file, 'r', encoding='utf-8') as f:
        form_data = f.read()
        
    with open(mermaid_file, 'r', encoding='utf-8') as f:
        mermaid_content = f.read()
    
    # Extract fields from both forms
    preform_fields = extract_form_fields(preform_html_content)
    main_mapping = create_field_mapping(main_html_content, form_data, mermaid_content)
    
    # Create a simplified mapping for preform fields
    preform_mapping = {}
    for field in preform_fields:
        preform_mapping[field.variable_name] = {
            "title": field.title,
            "help_text": field.help_text,
            "field_type": field.field_type,
            "form_variable": field.variable_name,
            "options": [
                {'value': '1', 'text': 'Ja'},
                {'value': '0', 'text': 'Nej'},
            ] if field.field_type == "ftype_checkbox" else field.options,
            "stage": "PREFORM",  # Special stage for preform fields
            "prompt_group": "Research Areas and Conditions"  # Group all preform fields together
        }
    
    # Combine both mappings
    combined_mapping = {**preform_mapping, **main_mapping}
    
    # Print debug information if verbose
    if verbose:
        logger.info("\nPreform Fields:")
        logger.info("==============")
        for var_name, info in preform_mapping.items():
            logger.info(f"\nField: {var_name}")
            logger.info(f"Title: {info['title']}")
            logger.info(f"Help Text: {info['help_text']}")
            if info['options']:
                logger.info("Options: " + ", ".join(f"{option['value']}: {option['text']}" for option in info['options']))
            logger.info("-" * 80)
            
        logger.info("\nMain Form Mappings:")
        logger.info("==================")
        for var_name, info in main_mapping.items():
            logger.info(f"\nField, form variable, field type: {var_name}, {info['form_variable']}, {info['field_type']}")
            logger.info(f"Title: {info['title']}")
            logger.info(f"Help Text: {info['help_text']}")
            logger.info(f"Character Limit: {info['char_limit']}")
            logger.info(f"Stage: {info['stage']}")
            logger.info(f"Prompt Group: {info['prompt_group']}")
            if info['options']:
                logger.info("Options: " + ", ".join(f"{option['value']}: {option['text']}" for option in info['options']))
            logger.info("-" * 80)

        for var_name, info in combined_mapping.items():
            if "[" in info['title']:
                logger.info(f"Title: {info['title']}")

        # Validate field hierarchy for main form fields only
        validate_field_hierarchy(main_mapping)
        
        # Sum character limits by prompt group
        prompt_group_limits = {}
        for var_name, info in combined_mapping.items():
            prompt_group = info.get('prompt_group', '')
            char_limit = info.get('char_limit', 0)
            if prompt_group:  # Only count fields that belong to a prompt group
                prompt_group_limits[prompt_group] = prompt_group_limits.get(prompt_group, 0) + char_limit
        
        logger.info("\nCharacter Limits by Prompt Group:")
        logger.info("================================")
        for group, limit in sorted(prompt_group_limits.items()):
            logger.info(f"{group}: {limit} characters")
    
    return combined_mapping

def _extract_question_number(title: str) -> Optional[str]:
    """Extract the question number from a field title."""
    # Look for patterns like "14.1.5" at the start of the title
    match = re.match(r'^(\d+\.\d+(?:\.\d+)?(?:\.\d+)?)\s*(?:\[.*?\])?\s*', title)
    if match:
        number = match.group(1)
        logger.debug(f"Processing question number: {number}")
        logger.debug(f"From title: {title}")
        return number
    return None

def _get_parent_numbers(number: str) -> List[str]:
    """Get all parent question numbers for a given number."""
    parts = number.split('.')
    parents = []
    for i in range(1, len(parts)):
        parent = '.'.join(parts[:i])
        parents.append(parent)
        logger.debug(f"Found parent {parent} for question {number}")
    return parents

def _validate_question_hierarchy(fields: List[FormField]) -> None:
    """Validate that all parent questions exist for child questions."""
    question_numbers = {
        _extract_question_number(field.title)
        for field in fields 
        if _extract_question_number(field.title)
    }
    
    logger.debug("\nDEBUG: All question numbers found:")
    logger.debug(f"All question numbers found: {sorted(list(question_numbers))}")
    
    for field in fields:
        number = _extract_question_number(field.title)
        if number:
            parents = _get_parent_numbers(number)
            for parent in parents:
                if parent not in question_numbers:
                    logger.warning(f"Missing parent question {parent} for question {number}")

def main():
    mapping = load_and_create_mappings(verbose=True)

if __name__ == "__main__":
    main()