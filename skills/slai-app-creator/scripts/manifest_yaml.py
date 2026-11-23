#!/usr/bin/env python3
"""Parse one JSON-compatible YAML document in a resource-limited child."""
import datetime
import json
import sys

from yaml_limits import (MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, YamlLimitError,
                         apply_resource_limits, bounded_loader)


def encode_date(value):
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    raise TypeError('manifest must contain JSON-compatible values')


def main():
    apply_resource_limits()
    import yaml
    data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        return {'ok': False, 'category': 'limits'}
    loader = None
    try:
        loader = bounded_loader(data)
        document = loader.get_single_data()
        result = {'ok': True, 'document': document}
        encoded = json.dumps(result, default=encode_date, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(encoded) > MAX_OUTPUT_BYTES:
            return {'ok': False, 'category': 'limits'}
        sys.stdout.buffer.write(encoded)
        return None
    except yaml.YAMLError as error:
        result = {'ok': False, 'category': 'invalid_yaml'}
        mark = getattr(error, 'problem_mark', None)
        if mark is not None and isinstance(mark.line, int) and isinstance(mark.column, int):
            result.update(line=mark.line, column=mark.column)
        return result
    except (YamlLimitError, MemoryError, RecursionError, TypeError, ValueError):
        return {'ok': False, 'category': 'limits'}
    finally:
        if loader is not None:
            loader.dispose()


if __name__ == '__main__':
    result = main()
    if result is not None:
        print(json.dumps(result))
