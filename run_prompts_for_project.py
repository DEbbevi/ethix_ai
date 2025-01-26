import os
import re
import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import anthropic
from extract_form import load_and_create_mappings
from utils import extract_text_from_files
import json
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

@dataclass
class ClaudeConfig:
    """Configuration for Claude API."""
    api_key: str
    max_retries: int = 3
    retry_delay: float = 1.0
    max_tokens: int = 4096
    temperature: float = 0
    sonnet_model: str = "claude-3-5-sonnet-latest"
    haiku_model: str = "claude-3-5-haiku-latest"

class ClaudeAPIError(Exception):
    """Base exception for Claude API errors."""
    pass

class ClaudeClient:
    """Wrapper for Claude API interactions."""
    
    def __init__(self, config: ClaudeConfig):
        self.config = config
        self.client = anthropic.Anthropic(api_key=config.api_key)
    
    def call_with_retry(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        model: Optional[str] = None
    ) -> str:
        """Make API call with retry logic with exponential backoff for rate limits."""
        retries = 0
        model = model or self.config.sonnet_model
        
        while retries < self.config.max_retries:
            try:
                messages = [{"role": "user", "content": prompt}]
                system = []
                
                if system_message:
                    system.append({
                        "type": "text",
                        "text": system_message,
                        "cache_control": {"type": "ephemeral"}
                    })
                
                response = self.client.messages.create(
                    model=model,
                    max_tokens=self.config.max_tokens,
                    system=system,
                    messages=messages,
                    temperature=self.config.temperature
                )
                return response.content[0].text
                
            except anthropic.RateLimitError as e:
                retries += 1
                if retries == self.config.max_retries:
                    raise ClaudeAPIError(f"Rate limit exceeded after {retries} retries: {str(e)}")
                # Exponential backoff: 2^retries * base_delay
                backoff_delay = self.config.retry_delay * (2 ** (retries - 1))
                logger.warning(f"Rate limit hit. Retry {retries}/{self.config.max_retries} after {backoff_delay}s delay: {str(e)}")
                time.sleep(backoff_delay)
            except Exception as e:
                retries += 1
                if retries == self.config.max_retries:
                    raise ClaudeAPIError(f"Failed after {retries} retries: {str(e)}")
                logger.warning(f"Retry {retries}/{self.config.max_retries} after error: {str(e)}")
                time.sleep(self.config.retry_delay * retries)

class EthicsProcessor:
    """Main processor for ethics application prompts."""
    
    def __init__(self, claude_client: ClaudeClient):
        self.claude = claude_client
        self.field_mapping = load_and_create_mappings()
        self.forskningsomrade_response = None  # Initialize the attribute
    
    def get_system_context(self, scientific_material: str) -> str:
        """Generate system context with scientific material."""
        return f"""Du är en forskningsassistent med särskild kompetens inom etikprövningsansökningar.
        Du ska hjälpa till att formulera svar på svenska för en etikprövningsansökan. Du ska basera dina svar på material om ett forskningsprojekt. Skriv svar i löpande text och undvik punktlistor.
        
        Här är forskningsmaterialet som du ska basera dina svar på:
        <material>
        {scientific_material}
        </material>"""
    
    def process_forskningsomrade(self, scientific_material: str) -> str:
        """Process forskningsomrade.txt prompt."""
        try:
            with open('prompts/forskningsomrade.txt', 'r', encoding='utf-8') as f:
                prompt_content = f.read()
            
            response = self.claude.call_with_retry(
                prompt=prompt_content,
                system_message=self.get_system_context(scientific_material)
            )
            self.forskningsomrade_response = response  # Store the response
            return response
        except Exception as e:
            logger.error(f"Error processing forskningsomrade: {e}")
            raise

    def process_remaining_prompts(self, scientific_material: str) -> Dict[str, str]:
        """Process all remaining prompts in parallel with progress bar (max 3 concurrent)."""
        prompt_files = get_prompt_files()
        if 'forskningsomrade.txt' in prompt_files:
            del prompt_files['forskningsomrade.txt']
        
        # First process forskningsomrade to get category selections
        forskningsomrade_tags = extract_xml_tags(self.forskningsomrade_response)
        
        # Remove conditional prompts based on forskningsomrade selections
        should_process_djurforsok = any(
            forskningsomrade_tags.get(tag, '0') == '1' 
            for tag in ['naturvetenskap', 'medicin_halsa', 'biologiskt_material', 
                       'joniserande_stralning', 'medicinteknik']
        )
        if not should_process_djurforsok and 'djurforsok.txt' in prompt_files:
            del prompt_files['djurforsok.txt']
            
        biologiskt_material_selected = forskningsomrade_tags.get('biologiskt_material', '0') == '1'
        if not biologiskt_material_selected:
            prompt_files.pop('nyinsamling_biologiskt_material.txt', None)
            prompt_files.pop('befintligt_biologiskt_material.txt', None)
            
        joniserande_stralning_selected = forskningsomrade_tags.get('joniserande_stralning', '0') == '1'
        if not joniserande_stralning_selected:
            prompt_files.pop('stralningsinformation.txt', None)
        
        system_context = self.get_system_context(scientific_material)
        
        # Create progress bar before starting parallel processing
        pbar = tqdm(total=len(prompt_files), desc="Processing prompts")
        
        # Use max_workers=3 to limit concurrent executions
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(
                    self._process_single_prompt,
                    filename,
                    content,
                    system_context
                ): filename
                for filename, content in prompt_files.items()
            }
            
            return self._collect_responses(futures, pbar)
    
    def _collect_responses(self, futures: Dict[Any, str], pbar: tqdm) -> Dict[str, str]:
        """Collect and combine responses from futures with progress updates."""
        all_responses = {}
        submitted_order = list(futures.values())  # Keep track of original submission order
        
        # Process responses as they complete (may be in any order)
        for i, future in enumerate(as_completed(futures)):
            filename = futures[future]
            original_position = submitted_order.index(filename) + 1
            try:
                pbar.set_description(f"Processing {filename} (submitted #{original_position}/{len(submitted_order)})")
                tags = future.result()
                all_responses.update(tags)
                pbar.update(1)
            except Exception as exc:
                logger.error(f"Error processing {filename} (submitted #{original_position}): {exc}")
                pbar.update(1)
        pbar.close()
        return all_responses
    
    def _process_single_prompt(
        self,
        filename: str,
        prompt_content: str,
        system_context: str
    ) -> Dict[str, str]:
        """Process a single prompt file."""
        logger.info(f"Processing prompt: {filename}")
        
        try:
            response = self.claude.call_with_retry(
                prompt=prompt_content,
                system_message=system_context
            )
            
            tags = extract_xml_tags(response)
            processed_tags = self._process_tags(filename, tags)
            
            # Add check for missing tags
            check_missing_tags(prompt_content, processed_tags, filename)
            
            return processed_tags
            
        except Exception as e:
            logger.error(f"Error processing {filename}: {e}")
            return {}
    
    def _process_tags(self, filename: str, tags: Dict[str, str]) -> Dict[str, str]:
        """Process and validate tags from a response."""
        for tag_id, content in list(tags.items()):
            char_limit = self._get_char_limit(tag_id)
            if char_limit > 0 and len(content) > char_limit:
                processed_content = self._shorten_content(tag_id, content, char_limit)
                tags[tag_id] = processed_content
        
        self._validate_required_tags(filename, tags)
        return tags
    
    def _get_char_limit(self, tag_id: str) -> int:
        """Get character limit for a tag."""
        for field_info in self.field_mapping.values():
            if field_info.get('question_id') == tag_id:
                return field_info.get('char_limit', 0)
        return 0
    
    def _shorten_content(self, tag_id: str, content: str, char_limit: int) -> str:
        """Shorten content using Haiku and truncation if needed."""
        logger.info(f"Content for tag {tag_id} exceeds limit ({len(content)} > {char_limit}). Attempting to shorten...")
        
        shorten_prompt = get_shorten_prompt(content, char_limit)
        shortened_content = self.claude.call_with_retry(
            prompt=shorten_prompt,
            model=self.claude.config.haiku_model
        )
        
        return safe_truncate_content(shortened_content, char_limit)
    
    def _validate_required_tags(self, filename: str, tags: Dict[str, str]) -> None:
        """Validate that all required tags are present."""
        prompt_group = self.field_mapping.get(filename, {}).get('prompt_group', '')
        if prompt_group:
            expected_tags = [
                field_info['question_id']
                for field_info in self.field_mapping.values()
                if field_info.get('prompt_group') == prompt_group
            ]
            
            for tag in expected_tags:
                if tag not in tags:
                    logger.warning(f"Missing expected tag {tag} in response from {filename}")

def get_prompt_files() -> Dict[str, str]:
    """Get all prompt files from the prompts directories."""
    prompt_files = {}
    prompt_dirs = ['prompts/']
    
    for dir_path in prompt_dirs:
        if os.path.exists(dir_path):
            for filename in os.listdir(dir_path):
                if filename.endswith('.txt'):
                    with open(os.path.join(dir_path, filename), 'r', encoding='utf-8') as f:
                        prompt_files[filename] = f.read()
    
    return prompt_files

def extract_xml_tags(response_text: str) -> Dict[str, str]:
    """Extract all XML tags and their content from the response."""
    # Pattern that matches both numeric (e.g., "14.1.2") and alphabetic (e.g., "BackgroundAndPurpose") tags
    pattern = r'<((?:\d+(?:\.\d+)*)|(?:[A-Za-z]+(?:And[A-Za-z]+)*)?)>(.*?)</\1>'
    matches = re.findall(pattern, response_text, re.DOTALL)
    
    tags = {}
    for tag_name, content in matches:
        tags[tag_name] = content.strip()
    
    return tags

def validate_char_limits(tags: Dict[str, str], field_mapping: Dict[str, Dict]) -> List[str]:
    """Validate character limits for each tag based on field mapping."""
    violations = []
    
    for tag_id, content in tags.items():
        # Find corresponding field in mapping
        for field_info in field_mapping.values():
            if field_info.get('question_id') == tag_id:
                char_limit = field_info.get('char_limit', 0)
                if char_limit > 0 and len(content) > char_limit:
                    violations.append(
                        f"Warning: Tag {tag_id} exceeds character limit of {char_limit} "
                        f"(current: {len(content)})"
                    )
                break
    
    return violations

def safe_truncate_content(content: str, char_limit: int) -> str:
    """
    Safely truncate content to fit within character limit while preserving XML structure.
    Only truncates if char_limit > 0.
    """
    if char_limit <= 0 or len(content) <= char_limit:
        return content
        
    # Find the last space before the limit
    truncate_point = content[:char_limit-3].rfind(' ')
    if truncate_point == -1:
        truncate_point = char_limit
        
    truncated = content[:truncate_point] + "..."
    return truncated

def get_shorten_prompt(content: str, char_limit: int) -> str:
    """Generate the prompt for shortening content."""
    current_length = len(content)
    chars_to_remove = current_length - char_limit
    
    return f"""
Du är en expert på att förkorta text samtidigt som du bevarar all viktig information. 
Förkorta följande text så att den är under {char_limit} tecken (nuvarande längd är {current_length} tecken, så ungefär {chars_to_remove} tecken behöver tas bort). 
Behåll all väsentlig information genom att omformulera och gör texten mer koncis.

Original text:
{content}

Viktigt:
1. Bevara all väsentlig information
2. Gör texten mer koncis genom att omformulera
3. Resultatet måste vara under {char_limit} tecken (du behöver ta bort ca {chars_to_remove} tecken)
4. Behåll samma språkliga ton och akademiska nivå
"""

def clean_conditional_responses(responses: Dict[str, str], field_mapping: Dict[str, Dict]) -> Dict[str, str]:
    """Remove responses that don't meet their conditional requirements."""
    cleaned_responses = responses.copy()
    
    # Map of parent questions and their required values for child questions
    conditional_map = {
        '14.1': {'required_value': '1', 'children': [
            '14.1.2', '14.1.2.1', '14.1.3', '14.1.4', '14.1.5', '14.1.6', 
            '14.1.7', '14.1.8', '14.1.9', '14.1.10', '14.1.12'
        ]},
        '14.1.2': {'required_value': '1', 'children': ['14.1.2.1']},
        '14.2': {'required_value': '1', 'children': [
            '14.2.2', '14.2.3', '14.2.4', '14.2.6', '14.2.7', 
            '14.2.8', '14.2.9', '14.2.10'
        ]},
        '9.1': {'required_value': '1', 'children': ['9.1.1']},
        '9.1': {'required_value': '2', 'children': ['9.1.2']},
        '9.3': {'required_value': '1', 'children': ['9.3.1', '9.3.2']},
        '10.1': {'required_value': '1', 'children': ['10.1.1', '10.1.2']},
        '11.1': {'required_value': '1', 'children': ['11.1.1']},
        '11.1': {'required_value': '2', 'children': ['11.1.2']},
        '1.7': {'required_value': '2', 'children': ['1.7.2']},
        '8.10': {'required_value': '1', 'children': ['8.10.1']},
        '2.5.5': {'required_value': '1', 'children': ['2.5.5.1']},
        '3.4': {'required_value': '1', 'children': ['3.4.3']},
    }
    
    # Additional category-based cleaning
    category_conditions = {
        'djurforsok': {
            'any_of': ['naturvetenskap', 'medicin_halsa', 'biologiskt_material', 
                      'joniserande_stralning', 'medicinteknik'],
            'required_value': '1',
            'tags': ['11.1', '11.1.1', '11.1.2']
        },
        'biologiskt_material': {
            'tag': 'biologiskt_material',
            'required_value': '1',
            'tags': ['14.1', '14.1.2', '14.1.2.1', '14.1.3', '14.1.4', '14.1.5', 
                    '14.1.6', '14.1.7', '14.1.8', '14.1.9', '14.1.10', '14.1.12',
                    '14.2', '14.2.2', '14.2.3', '14.2.4', '14.2.6', '14.2.7', 
                    '14.2.8', '14.2.9', '14.2.10']
        },
        'joniserande_stralning': {
            'tag': 'joniserande_stralning',
            'required_value': '1',
            'tags': ['15.2.1', '15.2.2', '15.2.4', '15.5', '15.6']
        }
    }
    
    # Clean based on category conditions
    for category, config in category_conditions.items():
        should_keep = False
        if 'any_of' in config:
            should_keep = any(
                cleaned_responses.get(tag, '0') == config['required_value']
                for tag in config['any_of']
            )
        else:
            should_keep = cleaned_responses.get(config['tag'], '0') == config['required_value']
            
        if not should_keep:
            for tag in config['tags']:
                if tag in cleaned_responses:
                    logger.info(f"Removing {tag} because category {category} condition not met")
                    del cleaned_responses[tag]
    
    # Clean based on parent-child conditions
    for parent, config in conditional_map.items():
        if parent in cleaned_responses:
            parent_value = str(cleaned_responses[parent]).strip()
            if parent_value != config['required_value']:
                for child in config['children']:
                    if child in cleaned_responses:
                        logger.info(f"Removing {child} because {parent}={parent_value} (required: {config['required_value']})")
                        del cleaned_responses[child]
    
    return cleaned_responses

def process_ethics_application(scientific_material: str, api_key: str) -> Dict[str, str]:
    """
    Process an ethics application with the given scientific material.
    
    Args:
        scientific_material: The text content to base the ethics application on
        api_key: The Anthropic API key
    
    Returns:
        Dict containing all responses with their tags
    """
    config = ClaudeConfig(api_key=api_key)
    claude_client = ClaudeClient(config)
    processor = EthicsProcessor(claude_client)
    
    # Process forskningsomrade
    base_response = processor.process_forskningsomrade(scientific_material)
    logger.info("Completed forskningsomrade processing")
    
    # Extract values from tags in forskningsomrade response
    forskningsomrade_data = {
        'dsd_8384': re.search(r'<naturvetenskap>(.*?)</naturvetenskap>', base_response, re.DOTALL).group(1).strip(),
        'dsd_8385': re.search(r'<teknik>(.*?)</teknik>', base_response, re.DOTALL).group(1).strip(), 
        'dsd_8383': re.search(r'<medicin_halsa>(.*?)</medicin_halsa>', base_response, re.DOTALL).group(1).strip(),
        'dsd_8387': re.search(r'<lantbruk_veterinar>(.*?)</lantbruk_veterinar>', base_response, re.DOTALL).group(1).strip(),
        'dsd_8386': re.search(r'<samhallsvetenskap>(.*?)</samhallsvetenskap>', base_response, re.DOTALL).group(1).strip(),
        'dsd_8382': re.search(r'<humaniora_konst>(.*?)</humaniora_konst>', base_response, re.DOTALL).group(1).strip(),
        'dsd_8379': re.search(r'<biologiskt_material>(.*?)</biologiskt_material>', base_response, re.DOTALL).group(1).strip(),
        'dsd_8380': re.search(r'<joniserande_stralning>(.*?)</joniserande_stralning>', base_response, re.DOTALL).group(1).strip(),
        'dsd_8381': re.search(r'<medicinteknik>(.*?)</medicinteknik>', base_response, re.DOTALL).group(1).strip()
    }
    
    for field_id, response_value in forskningsomrade_data.items():
        value = 1 if str(response_value).lower() in ['yes', 'true', '1', 'ja'] else 0
        forskningsomrade_data[field_id] = value

    # Save extracted values to JSON
    with open('forskningsomrade_response.json', 'w', encoding='utf-8') as f:
        json.dump(forskningsomrade_data, f, ensure_ascii=False, indent=4)
    logger.info("Saved forskningsomrade tag values to JSON")
    
    # Process remaining prompts
    responses = processor.process_remaining_prompts(scientific_material)
    logger.info("Completed processing all remaining prompts")

    # Combine all responses
    all_responses = {
        'forskningsomrade': base_response,
        **responses
    }
    
    # Clean conditional responses
    cleaned_responses = clean_conditional_responses(all_responses, processor.field_mapping)
    
    # Save responses to JSON
    with open('all_responses.json', 'w', encoding='utf-8') as f:
        json.dump(cleaned_responses, f, ensure_ascii=False, indent=4)
    logger.info("Saved cleaned responses to JSON")
    
    return cleaned_responses

def main():
    try:
        scientific_material = extract_text_from_files([
            "projektplan.docx",
        ])
    except ValueError as e:
        logger.error(f"Failed to extract text from files: {e}\n\nUsing default Loperamide text instead.")
        scientific_material = """ABSTRACT
Objective: To compare efficacy and tolerability of a loperamide/simethicone (LOP/SIM) combination product with that of 
loperamide (LOP) alone, simethicone (SIM) alone, and placebo (PBO) for acute nonspecific diarrhea with gas-related abdominal discomfort.
Research design and methods: In this multicenter, double-blind, 48‑h study, patients were randomly assigned to receive two 
tablets, each containing either LOP/SIM 2 mg/125 mg (n = 121), LOP 2 mg (n = 120), SIM 125 mg (n = 123), or PBO (n = 121), 
followedby one tablet after each unformed stool, up to four tablets in any 24‑h period. The primary outcome measures were 
time to last unformed stool and time to complete relief of gas-related abdominal discomfort. For time to last unformed stool, 
an unformed stool after a 24‑h period of formed stools or no stools was considered a continuance of the original episode 
(stricter definition) or a new episode (alternate definition).
Results: A total of 483 patients were included in the intent-to-treat analysis. The median time to last unformed stool for 
LOP/SIM (7.6 h) was significantly shorter than that of LOP (11.5 h), SIM (26.0 h), and PBO (29.4 h) ( p ≤ 0.0232 in comparison 
with survival curves) using the alternate definition; it was numerically but not significantly shorter than that of LOP 
( p = 0.0709) and significantly shorter than that of SIM and PBO ( p = 0.0001) using the stricter definition. LOP/SIM-treated 
patients had a shorter time to complete relief of gas-related abdominal discomfort than patients who received either ingredient 
alone or placebo (all p = 0.0001). Few patients reported adverse events in the four treatment groups, none of which were serious 
in nature. Potential study limitations include the ability to generalize study results to the population at large, variability 
in total dose consumed, and subjectivity of patient diary data.
Conclusions: LOP/SIM was well-tolerated and more efficacious than LOP alone, SIM alone, or placebo for acute nonspecific 
diarrhea and gas-related abdominal discomfort."""
        
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        return
        
    responses = process_ethics_application(scientific_material, api_key)
    
    # Print results
    for tag_id, content in responses.items():
        print(f"\nTag: {tag_id}")
        print("-" * 40)
        print(content)

def extract_expected_tags_from_prompt(prompt_content: str) -> List[str]:
    """Extract expected tag IDs from a prompt file."""
    # Skip the <information> section
    content = re.sub(r'<information>.*?</information>', '', prompt_content, flags=re.DOTALL)
    
    # Look for FrågeID patterns and XML tags in example responses
    frageids = re.findall(r'FrågeID:\s*<([^>]+)>', content)
    example_tags = re.findall(r'<(\d+(?:\.\d+)*?)>', content)
    
    # Combine and deduplicate tags
    all_tags = set(frageids + example_tags)
    return sorted(list(all_tags))

def check_missing_tags(prompt_content: str, extracted_tags: Dict[str, str], filename: str) -> None:
    """Check for missing tags that were expected in the response."""
    expected_tags = extract_expected_tags_from_prompt(prompt_content)
    extracted_tag_ids = set(extracted_tags.keys())
    
    missing_tags = set(expected_tags) - extracted_tag_ids
    if missing_tags:
        logger.warning(f"Missing expected tags in response from {filename}: {', '.join(sorted(missing_tags))}")

if __name__ == "__main__":
    main()
