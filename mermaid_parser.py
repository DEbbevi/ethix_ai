import re
from typing import Dict, Set
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import logging


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

def create_flow_stage_enum(mermaid_content: str) -> type:
    """Dynamically create FlowStage enum from Mermaid content."""
    stages = []
    
    # Find all top-level subgraphs (main stages)
    stage_pattern = r'subgraph\s+"([^"]+)"'
    for line in mermaid_content.split('\n'):
        match = re.search(stage_pattern, line.strip())
        if match and any(keyword in match.group(1) for keyword in ["FÖRUTSÄTTNING", "KÖRNING"]):
            stage_name = match.group(1)
            # Convert to enum-friendly format
            enum_name = (stage_name
                        .replace(":", "")
                        .replace(" ", "_")
                        .replace("Ö", "O")
                        .replace("Ä", "A")
                        .upper())
            stages.append((enum_name, stage_name))
    
    return Enum('FlowStage', stages)

@dataclass
class PromptGroup:
    name: str
    questions: List[str]
    stage: Optional['FlowStage']
    dependencies: List[str]
    can_run_parallel: bool = False

# Load Mermaid content and create FlowStage enum
try:
    with open('forms/flow.mermaid', 'r', encoding='utf-8') as f:
        mermaid_content = f.read()
    FlowStage = create_flow_stage_enum(mermaid_content)
except FileNotFoundError:
    # Fallback for when file isn't available (e.g., during testing)
    FlowStage = Enum('FlowStage', [
        ('FORUTSATTNING', 'FÖRUTSÄTTNING'),
        ('KORNING_1', 'KÖRNING 1: Krävs för riskbedömning'),
        ('KORNING_1_PARALLELLT', 'KÖRNING 1 PARALLELLT'),
        ('KORNING_2', 'KÖRNING 2'),
        ('KORNING_3', 'KÖRNING 3')
    ])

def parse_mermaid_flow(mermaid_content: str) -> Dict[str, PromptGroup]:
    """Parse mermaid flow diagram to extract prompt groups and their relationships."""
    
    # Track current subgraph (stage) and dependencies
    current_stage = None
    stage_stack = []
    dependencies: Dict[str, Set[str]] = {}
    groups: Dict[str, Dict] = {}  # Changed to store both questions and stage
    current_group = None
    group_stack = []
    
    # Regular expressions for parsing
    stage_pattern = r'subgraph\s+"([^"]+)"'
    group_pattern = r'subgraph\s+"([^"]+)"'
    node_pattern = r'([A-Z]\d+(?:a)?)\["([^"]+)"\]'
    dependency_pattern = r'(\w+)\s*-->\s*(\w+)'
    question_pattern = r'(\d+\.\d+(?:\.\d+)?)'
    
    lines = mermaid_content.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        #print(f"\nProcessing line: {line}")
        
        # Check for stage
        stage_match = re.search(stage_pattern, line)
        if stage_match:
            stage_name = stage_match.group(1)
            try:
                new_stage = FlowStage(stage_name)
                current_stage = new_stage
                stage_stack.append(current_stage)
                #print(f"Found stage: {stage_name}")
            except ValueError:
                # This is a subgraph within a stage
                group_name = stage_name.lower().replace(" ", "_")
                if current_stage:
                    if group_name not in groups:
                        groups[group_name] = {
                            'questions': [],
                            'stage': current_stage
                        }
                    current_group = group_name
                    group_stack.append(current_group)
                    #print(f"Found group: {group_name} in stage {current_stage.name}")
            continue
        
        # Check for end of subgraph
        if line == "end":
            if group_stack:
                old_group = group_stack.pop()
                #print(f"End of group: {old_group}")
                current_group = group_stack[-1] if group_stack else None
            elif stage_stack:
                old_stage = stage_stack.pop()
                #print(f"End of stage: {old_stage.name}")
                current_stage = stage_stack[-1] if stage_stack else None
            continue
        
        # Check for node with questions
        node_match = re.search(node_pattern, line)
        if node_match and current_group:
            node_id = node_match.group(1)
            node_content = node_match.group(2)
            #print(f"Found node {node_id} in group {current_group}: {node_content}")
            
            # Extract question number from node content
            question_match = re.search(question_pattern, node_content)
            if question_match:
                question_id = question_match.group(1)
                if current_group not in groups:
                    groups[current_group] = {
                        'questions': [],
                        'stage': current_stage
                    }
                if question_id not in groups[current_group]['questions']:
                    groups[current_group]['questions'].append(question_id)
                    #print(f"Added question {question_id} to group {current_group}")
        
        # Check for dependencies
        dep_match = re.search(dependency_pattern, line)
        if dep_match:
            source, target = dep_match.group(1), dep_match.group(2)
            if source not in dependencies:
                dependencies[source] = set()
            dependencies[source].add(target)
            #print(f"Found dependency: {source} -> {target}")
    
    # Print parsed groups
    logger.info("\nParsed groups:")
    logger.info("-------------")
    for group_name, group_data in groups.items():
        logger.info(f"Group {group_name}: {group_data['questions']} (Stage: {group_data['stage'].name if group_data['stage'] else 'None'})")
    
    # Create PromptGroups
    prompt_groups = {}
    for group_name, group_data in groups.items():
        prompt_groups[group_name] = PromptGroup(
            name=group_name,
            questions=sorted(group_data['questions']),  # Sort questions for consistent ordering
            stage=group_data['stage'],
            dependencies=list(dependencies.get(group_name, set())),
            can_run_parallel=(group_data['stage'] and 'PARALLELLT' in group_data['stage'].value)
        )
    
    return prompt_groups

def load_prompt_groups() -> Dict[str, PromptGroup]:
    """Load and parse the mermaid flow diagram to create prompt groups."""
    with open('forms/flow.mermaid', 'r', encoding='utf-8') as f:
        mermaid_content = f.read()
    
    return parse_mermaid_flow(mermaid_content) 