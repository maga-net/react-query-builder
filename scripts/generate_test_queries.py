import argparse
import json
import os
import random
import uuid

# --- Configuration ---
# Realistic field definitions for a sample application
FIELDS = [
    {"name": "firstName", "label": "First Name", "type": "text"},
    {"name": "lastName", "label": "Last Name", "type": "text"},
    {"name": "age", "label": "Age", "type": "number"},
    {"name": "birthDate", "label": "Birth Date", "type": "date"},
    {"name": "isMusician", "label": "Is a musician", "type": "boolean"},
    {"name": "instrument", "label": "Instrument", "type": "select", "values": ["Guitar", "Piano", "Drums", "Violin"]},
    {"name": "department", "label": "Department", "type": "multiselect", "values": ["HR", "Engineering", "Marketing", "Sales"]},
]

# Standard operators from react-query-builder
OPERATORS = {
    "text": ["=", "!=", "contains", "beginsWith", "endsWith"],
    "number": ["=", "!=", "<", ">", "<=", ">="],
    "date": ["=", "!=", "<", ">"],
    "boolean": ["="],
    "select": ["=", "!="],
    "multiselect": ["in", "notIn"],
}

COMBINATORS = ["and", "or"]

# --- Value Generators ---
def generate_random_value(field_config):
    """Generates a random value based on the field's type."""
    field_type = field_config["type"]
    if field_type == "text":
        return "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=random.randint(5, 15)))
    elif field_type == "number":
        return random.randint(18, 70)
    elif field_type == "date":
        year = random.randint(1950, 2010)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        return f"{year}-{month:02d}-{day:02d}"
    elif field_type == "boolean":
        return random.choice([True, False])
    elif field_type == "select":
        return random.choice(field_config["values"])
    elif field_type == "multiselect":
        sample_size = random.randint(1, len(field_config["values"]))
        return ",".join(random.sample(field_config["values"], k=sample_size))
    return None

# --- Query Generation Logic ---
def generate_rule():
    """Generates a single rule object."""
    field_config = random.choice(FIELDS)
    field_name = field_config["name"]
    operator = random.choice(OPERATORS[field_config["type"]])
    value = generate_random_value(field_config)
    return {
        "id": str(uuid.uuid4()),
        "field": field_name,
        "operator": operator,
        "value": value,
    }

def generate_query_group(max_depth, current_depth=0):
    """Recursively generates a query group."""
    num_elements = random.randint(1, 3)
    rules = []

    for _ in range(num_elements):
        # Decide whether to add a rule or a nested group
        if current_depth < max_depth and random.random() < 0.3: # 30% chance of a nested group
            rules.append(generate_query_group(max_depth, current_depth + 1))
        else:
            rules.append(generate_rule())

    return {
        "id": str(uuid.uuid4()),
        "combinator": random.choice(COMBINATORS),
        "rules": rules,
    }

# --- Main Execution ---
def main():
    """Main function to parse arguments and generate queries."""
    parser = argparse.ArgumentParser(description="Generate random react-query-builder query objects for testing.")
    parser.add_argument(
        "-n", "--number",
        type=int,
        default=1,
        help="Number of query files to generate."
    )
    parser.add_argument(
        "-d", "--depth",
        type=int,
        default=3,
        help="Maximum nesting depth of query groups."
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default="test/fixtures/generated",
        help="Directory to save the generated JSON files."
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Generating {args.number} query file(s) with max depth {args.depth} into '{args.output_dir}'...")

    for i in range(args.number):
        query = generate_query_group(max_depth=args.depth)
        filename = os.path.join(args.output_dir, f"generated_query_{i+1}.json")
        with open(filename, "w") as f:
            json.dump(query, f, indent=2)

    print("Done.")

if __name__ == "__main__":
    main()
