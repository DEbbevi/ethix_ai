# Swedish Research Ethics Documentation Generator

A system for generating and managing Swedish research ethics documentation, with support for Ethix, the information system of the Swedish ethical review authority.

![Workflow diagram showing the process flow from input documents through template processing to final output formats](https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F406bb032ca007fd1624f261af717d70e6ca86286-2401x1000.png&w=3840&q=75)
From [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents).

## Overview

This repo provides tools for:
- Generating documentation in multiple formats (Markdown, DOCX, PDF, Ethix backend compatible)
- Processing research ethics applications
- Managing research participant information and consent forms
- Handling biobank and biological material documentation
- GDPR-compliant data processing (Uses Anthropic's model suite)

## Features

- Support for template-based document generation (DOCX, PDF)
- Automated file naming and organization
- XML tag-based content replacement
- Support for the Swedish research ethics applications system Ethix
- Management of participant consent forms
- Handling of biological material documentation

## Demo & Quick Start

- [Try it in Google Colab](https://colab.research.google.com/drive/1pEhEoK1K1fWhtEvbMnCVfNFvO4NuJK_b?usp=sharing)


https://github.com/user-attachments/assets/7cb52b14-69aa-4a57-87e8-06793909e7c5



## Installation
```bash
pip install -r requirements.txt
```

## Usage

```python
from run_prompts_for_project import process_ethics_application
from generate_documentation import generate_documentation
from utils import extract_text_from_files
from extract_form import load_and_create_mappings
from create_ethix_application import main as create_application
import os

api_key = os.getenv("ANTHROPIC_API_KEY")

scientific_material = extract_text_from_files([
    "projektplan.docx", "cool_biobank_setup.pdf", "braindump_potential_future_implications.txt"
])
    
# Retrieve draft of ethics application
responses = process_ethics_application(scientific_material, api_key)

# Will output the full application draft in .docx and markdown .txt for 
# archiving, and research participant information in .docx if applicable.
generate_documentation(responses)

# Create a new project in Ethix and save draft of ethics application.
# load_and_create_mappings() creates field mapping dynamically for Ethix backend.
create_application(responses=responses, field_mapping=load_and_create_mappings())

```

## File Structure

- `generate_documentation.py`: Core documentation generation functionality
- `run_prompts_for_project.py`: Ethics processing and prompt handling
- `create_ethix_application.py`: Functionality for interfacing directly with ethix backend
- `prompts/`: Prompts for the LLM
- `forms/`: HTML templates etc for ethics application and workflow of the LLM
- `txt/`: Source documents and guidelines used to develop the prompts

## Research Ethics Principles

1. Research must respect human dignity
2. Human rights and fundamental freedoms must be considered
3. Human welfare takes precedence over society's and science's needs
4. Informed consent is required for participant research
5. Data protection and privacy must be maintained

### Propted To Produce Documents With

- Clear and accessible language
- Complete information for informed consent
- Compliance with ethical guidelines
- Balanced and non-persuasive presentation
- Clear communication of participant rights

## Contributing

Project is in early alpha. Some parts are duct taped (with style). Please contribute by creating a pull request.

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
