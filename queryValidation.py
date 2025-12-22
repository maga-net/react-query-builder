from typing import Any, Dict, List, Union, Optional

from dataclasses import dataclass


@dataclass
class ValidationError:
    """Represents a single validation error."""
    path: List[str]
    message: str
    field: Optional[str] = None


class QueryValidator:
    """Validates React Query Builder query objects."""

    def __init__(self, fields: List[Dict[str, Any]]):
        self.fields = {f['name']: f for f in fields}
        self.errors: List[ValidationError] = []

    def validate(self, query: Dict[str, Any], path: List[str] = None) -> List[ValidationError]:
        """Validate a query object and return list of validation errors."""
        self.errors = []
        path = path or []
        self._validate_query(query, path)
        return self.errors

    def _validate_query(self, query: Dict[str, Any], path: List[str]):
        if not isinstance(query, dict):
            self.errors.append(ValidationError(path, 'Query must be an object'))
            return

        if 'combinator' not in query:
            self.errors.append(ValidationError(path, 'Missing combinator'))
        elif query['combinator'] not in ['and', 'or']:
            self.errors.append(ValidationError(path, f'Invalid combinator: {query["combinator"]}'))

        if 'rules' not in query or not isinstance(query['rules'], list):
            self.errors.append(ValidationError(path, 'Missing or invalid rules array'))
            return

        for i, rule in enumerate(query['rules']):
            rule_path = path + [str(i)]
            self._validate_rule(rule, rule_path)

    def _validate_rule(self, rule: Any, path: List[str]):
        if isinstance(rule, dict):
            # Rule object
            if not all(key in rule for key in ['field', 'operator', 'value']):
                self.errors.append(ValidationError(path, 'Rule missing required fields: field, operator, value'))
                return

            if rule['field'] not in self.fields:
                self.errors.append(ValidationError(path, f'Unknown field: {rule["field"]}', 'field'))

            field_def = self.fields.get(rule['field'])
            if field_def and 'operators' in field_def and rule['operator'] not in field_def['operators']:
                self.errors.append(ValidationError(path, f'Invalid operator for field {rule["field"]}', 'operator'))

            if not rule['value']:
                self.errors.append(ValidationError(path, 'Value cannot be empty', 'value'))

        elif isinstance(rule, list):
            # Nested group
            self._validate_query(rule[0], path)
        else:
            self.errors.append(ValidationError(path, 'Invalid rule format'))

    def is_valid(self) -> bool:
        """Check if the last validated query is valid."""
        return len(self.errors) == 0


def validate_query(query: Dict[str, Any], fields: List[Dict[str, Any]]) -> List[ValidationError]:
    """Convenience function to validate a query."""
    validator = QueryValidator(fields)
    return validator.validate(query)
