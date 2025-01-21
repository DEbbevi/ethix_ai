import os
import re
import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import anthropic
from extract_form import load_and_create_mappings

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
        """Make API call with retry logic."""
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
    
    def get_system_context(self, scientific_material: str) -> str:
        """Generate system context with scientific material."""
        return f"""Du är en forskningsassistent med särskild kompetens inom etikprövningsansökningar.
        Du ska hjälpa till att formulera svar på svenska för en etikprövningsansökan. Du ska basera dina svar på material om ett forskningsprojekt.
        
        Här är forskningsmaterialet som du ska basera dina svar på:
        <material>
        {scientific_material}
        </material>"""
    
    def process_forskningsomrade(self, scientific_material: str) -> str:
        """Process forskningsomrade.txt prompt."""
        try:
            with open('prompts/forskningsomrade.txt', 'r', encoding='utf-8') as f:
                prompt_content = f.read()
            
            return self.claude.call_with_retry(
                prompt=prompt_content,
                system_message=self.get_system_context(scientific_material)
            )
        except Exception as e:
            logger.error(f"Error processing forskningsomrade: {e}")
            raise

    def process_remaining_prompts(self, scientific_material: str) -> Dict[str, str]:
        """Process all remaining prompts in parallel."""
        prompt_files = get_prompt_files()
        if 'forskningsomrade.txt' in prompt_files:
            del prompt_files['forskningsomrade.txt']
        
        system_context = self.get_system_context(scientific_material)
        
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(
                    self._process_single_prompt,
                    filename,
                    content,
                    system_context
                ): filename
                for filename, content in prompt_files.items()
            }
            
            return self._collect_responses(futures)
    
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
    
    def _collect_responses(self, futures: Dict[Any, str]) -> Dict[str, str]:
        """Collect and combine responses from futures."""
        all_responses = {}
        for future in as_completed(futures):
            filename = futures[future]
            try:
                tags = future.result()
                all_responses.update(tags)
            except Exception as exc:
                logger.error(f"Error processing {filename}: {exc}")
        return all_responses

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

def main():
    config = ClaudeConfig(api_key=os.getenv("ANTHROPIC_API_KEY"))
    claude_client = ClaudeClient(config)
    processor = EthicsProcessor(claude_client)
    
    scientific_material = "Your scientific material here"
    
    # Process forskningsomrade
    base_response = processor.process_forskningsomrade(scientific_material)
    logger.info("Completed forskningsomrade processing")
    
    # Process remaining prompts
    responses = processor.process_remaining_prompts(scientific_material)
    logger.info("Completed processing all remaining prompts")
    
    # Print results
    for tag_id, content in responses.items():
        print(f"\nTag: {tag_id}")
        print("-" * 40)
        print(content)

if __name__ == "__main__":
    main()
