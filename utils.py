import logging
from pathlib import Path
from typing import Union, List
import PyPDF2
import docx2txt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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