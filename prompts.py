# prompts.py

OUTPUT_FORMAT = {
    "tasks": [
        {"title": "Task name"}
    ],
    "priorities": [
        {"task": "Task name", "priority": "High"}
    ],
    "workflow_steps": [
        "Step 1",
        "Step 2",
        "Step 3"
    ]
}

EXTRACTION_GUIDELINES = """
The workflow extractor should:
1. Identify action items from raw text
2. Convert them into short task titles
3. Assign priorities using simple rules
4. Generate logical workflow steps
5. Return data in this structure:
   - tasks
   - priorities
   - workflow_steps
"""