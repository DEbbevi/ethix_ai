import os
import zipfile
from typing import Dict, List, Tuple, Union
import logging
from docx import Document
from docx.shared import Pt, RGBColor
import markdown
import PyPDF2
import docx2txt
from pathlib import Path
from run_prompts_for_project import EthicsProcessor, ClaudeClient, ClaudeConfig
from extract_form import load_and_create_mappings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def clean_title_for_filename(title: str) -> str:
    """Convert title to filename-friendly format, taking first 5 words."""
    # Remove any special characters and split into words
    words = ''.join(c if c.isalnum() or c.isspace() else ' ' for c in title).split()
    # Take first 5 words and join with underscore
    return '_'.join(words[:5])

def docx_replace(old_file: str, new_file: str, rep: Dict[str, str]) -> None:
    """Replace text in docx file using zipfile method."""
    try:
        with zipfile.ZipFile(old_file, 'r') as zin:
            with zipfile.ZipFile(new_file, 'w') as zout:
                for item in zin.infolist():
                    buffer = zin.read(item.filename)
                    if item.filename == 'word/document.xml':
                        content = buffer.decode('utf-8')
                        for tag, replacement_text in rep.items():
                            # Replace just the opening tag with the content
                            tag_placeholder = f"<{tag}>"
                            content = content.replace(tag_placeholder, replacement_text)
                        buffer = content.encode('utf-8')
                    zout.writestr(item, buffer)
        logger.info(f"Successfully created {new_file} with replacements")
    except Exception as e:
        logger.error(f"Error during docx replacement: {e}")
        raise

class DocumentGenerator:
    def __init__(self):
        self.field_mapping = load_and_create_mappings()
        
    def _get_heading_level(self, question_id: str) -> int:
        """Determine heading level based on question ID depth."""
        return len(question_id.split('.'))
    
    def _sort_responses(self, responses: Dict[str, str]) -> List[Tuple[str, str, str]]:
        """Sort responses by question ID and get titles."""
        sorted_items = []
        for question_id, content in responses.items():
            # Find the title from field mapping
            title = ""
            for field_info in self.field_mapping.values():
                if field_info.get('question_id') == question_id:
                    title = field_info['title']
                    break
            
            if title:
                sorted_items.append((question_id, title, content))
        
        # Sort by question ID numerically
        return sorted(sorted_items, key=lambda x: [int(n) for n in x[0].split('.')])
    
    def generate_markdown(self, responses: Dict[str, str]) -> str:
        """Generate markdown from responses."""
        markdown_content = []
        sorted_responses = self._sort_responses(responses)
        
        for question_id, title, content in sorted_responses:
            level = self._get_heading_level(question_id)
            heading = '#' * level
            markdown_content.append(f"{heading} {title}\n\n{content}\n")
        
        return '\n'.join(markdown_content)
    
    def save_markdown(self, markdown_content: str, output_file: str = 'output.txt'):
        """Save markdown content to file."""
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        logger.info(f"Markdown saved to {output_file}")
    
    def generate_docx(self, markdown_content: str, output_file: str = 'output.docx'):
        """Convert markdown to docx and save."""
        doc = Document()
        
        # Set default font
        style = doc.styles['Normal']
        style.font.name = 'Calibri'
        style.font.size = Pt(11)
        
        # Convert markdown to HTML first
        html = markdown.markdown(markdown_content)
        
        # Split by headers
        sections = html.split('<h')
        
        for section in sections:
            if not section.strip():
                continue
                
            # Process headers
            if section[0].isdigit():
                level = int(section[0])
                end_header = section.find('>')
                header_text = section[end_header+1:section.find('</h')]
                content = section[section.find('</h')+5:]
                
                # Add header with appropriate style
                doc.add_heading(header_text, level=level)
                
                # Add content
                if content.strip():
                    doc.add_paragraph(content.strip())
            else:
                # Just content without header
                if section.strip():
                    doc.add_paragraph(section.strip())
        
        # Save the document
        doc.save(output_file)
        logger.info(f"Document saved to {output_file}")

    def update_forskningspersonsinformation(self, responses: Dict[str, str]) -> None:
        """Update forskningspersonsinformation.docx with responses."""
        # Get the title from response 1.1 for the filename
        title = responses.get("1.1", "untitled")
        clean_title = clean_title_for_filename(title)
        output_file = f"FPI_{clean_title}.docx"
        
        # Create replacement dictionary with just the tag names as keys
        replacements = {
            "BackgroundAndPurpose": responses.get("BackgroundAndPurpose", ""),
            "ParticipantRequirements": responses.get("ParticipantRequirements", ""),
            "RisksAndConsequences": responses.get("RisksAndConsequences", ""),
            "DataManagement": responses.get("DataManagement", ""),
            "SampleHandling": responses.get("SampleHandling", ""),
            "ResultsAccess": responses.get("ResultsAccess", ""),
            "InsuranceAndCompensation": responses.get("InsuranceAndCompensation", ""),
            "title": responses.get("1.1", "")  # Map <title> to response from 1.1
        }
        
        # Perform the replacement
        try:
            docx_replace(
                old_file='forskningspersonsinformation_template.docx',
                new_file=output_file,
                rep=replacements
            )
            logger.info(f"Successfully created {output_file}")
        except Exception as e:
            logger.error(f"Failed to create {output_file}: {e}")
            raise

def extract_text_from_files(file_paths: Union[str, List[str]]) -> str:
    """
    Extract text from various file types (.doc, .docx, .pdf, .txt).
    Args:
        file_paths: Single file path or list of file paths
    Returns:
        Concatenated string of all text content
    """
    if isinstance(file_paths, str):
        file_paths = [file_paths]
    
    all_text = []
    
    for file_path in file_paths:
        try:
            path = Path(file_path)
            if not path.exists():
                logger.error(f"File not found: {file_path}")
                continue
                
            logger.info(f"Processing file: {file_path}")
            
            if path.suffix.lower() == '.pdf':
                # Handle PDF files
                with open(path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = []
                    for page in pdf_reader.pages:
                        text.append(page.extract_text())
                    all_text.append('\n'.join(text))
                    
            elif path.suffix.lower() in ['.doc', '.docx']:
                # Handle Word documents
                text = docx2txt.process(path)
                all_text.append(text)
                
            elif path.suffix.lower() == '.txt':
                # Handle text files
                with open(path, 'r', encoding='utf-8') as file:
                    text = file.read()
                    all_text.append(text)
                    
            else:
                logger.warning(f"Unsupported file type: {path.suffix}")
                continue
                
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            continue
    
    if not all_text:
        raise ValueError("No text could be extracted from the provided files")
    
    # Join all text with double newlines between documents
    combined_text = '\n\n'.join(all_text)
    logger.info(f"Successfully extracted text from {len(file_paths)} file(s)")
    
    return combined_text

def main():
    # Initialize Claude client
    config = ClaudeConfig(api_key=os.getenv("ANTHROPIC_API_KEY"))
    claude_client = ClaudeClient(config)
    processor = EthicsProcessor(claude_client)
    
    # Example usage with multiple files
    try:
        scientific_material = extract_text_from_files([
            "path/to/document1.pdf",
            "path/to/document2.docx",
            "path/to/document3.txt"
        ])
    except ValueError as e:
        logger.error(f"Failed to extract text from files: {e}")
        return
    
    # Process ethics application
    base_response = processor.process_forskningsomrade(scientific_material)
    responses = processor.process_remaining_prompts(scientific_material)
    
    # Combine all responses
    all_responses = {
        "forskningsomrade": base_response,
        **responses
    }
    
    # Generate documentation
    doc_generator = DocumentGenerator()
    
    # Generate and save markdown/docx
    markdown_content = doc_generator.generate_markdown(all_responses)
    doc_generator.save_markdown(markdown_content, 'output.txt')
    doc_generator.generate_docx(markdown_content, 'output.docx')
    
    # Update forskningspersonsinformation.docx
    doc_generator.update_forskningspersonsinformation(all_responses)

if __name__ == "__main__":
    main() 