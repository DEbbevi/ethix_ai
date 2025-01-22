# Swedish Research Ethics Documentation Generator

A system for generating and managing research ethics documentation, with specific support for Swedish research institutions.

## Overview

This project provides tools for:
- Generating documentation in multiple formats (Markdown, DOCX, PDF)
- Processing research ethics applications
- Managing research participant information and consent forms
- Handling biobank and biological material documentation
- GDPR-compliant data processing

## Features

### Documentation Generation
- Support for template-based document generation(DOCX, PDF)
- Custom styling and formatting for institutional requirements
- Automated file naming and organization
- XML tag-based content replacement

### Ethics Processing
- Support for the Swedish research ethics applications system Ethix
- Management of participant consent forms
- Handling of biological material documentation

## Installation
```bash
pip install -r requirements.txt
```

## Usage

### Generate Documentation

```python
from generate_documentation import DocumentGenerator

generator = DocumentGenerator()

# Generate DOCX from markdown
generator.generate_docx("your_research_content.md", "output.docx")

# Save as markdown
generator.save_markdown("your_research_content", "output.md")
```

### Ethics Processing

The system supports processing of ethics applications according to Swedish regulations and guidelines, including:
- Research participant information
- Consent management
- Biobank handling
- International collaboration

## File Structure

- `generate_documentation.py`: Core documentation generation functionality
- `run_prompts_for_project.py`: Ethics processing and prompt handling
- `create_ethix_application.py`: Functionality for interfacing directly with ethix backend
- `prompts/`: Templates and guidance documents
- `forms/`: HTML templates for ethics applications
- `txt/`: Reference documents and guidelines

## Guidelines

### Research Ethics Principles

1. Research must respect human dignity
2. Human rights and fundamental freedoms must be considered
3. Human welfare takes precedence over society's and science's needs
4. Informed consent is required for participant research
5. Data protection and privacy must be maintained

### Produces Documents With

- Clear and accessible language
- Complete information for informed consent
- Compliance with ethical guidelines
- Balanced and non-persuasive presentation
- Clear communication of participant rights

## Contributing

Please contribe to the project by creating a pull request.

## License

MIT License

Copyright (c) 2023

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
