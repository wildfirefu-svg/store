#!/usr/bin/env python3
"""
Merge new celebrity cases into the existing cases_real_db.json.
Validates format, deduplicates by ID, updates metadata.
"""

import json
import sys
import os
from datetime import date


def validate_case(case):
    """Validate a case has required fields. Returns list of errors."""
    errors = []
    if 'id' not in case:
        errors.append('missing id')
    if 'name' not in case:
        errors.append('missing name')
    if 'birth' not in case:
        errors.append('missing birth')
    else:
        b = case['birth']
        if 'datetime' not in b:
            errors.append('missing birth.datetime')
        if 'location' not in b:
            errors.append('missing birth.location')
    if 'gender' not in case:
        errors.append('missing gender')
    if 'events' not in case:
        errors.append('missing events')
    return errors


def merge_cases(existing_path, new_cases_path, output_path=None):
    """Merge new cases into existing DB."""
    # Load existing
    with open(existing_path, 'r', encoding='utf-8') as f:
        existing_db = json.load(f)

    existing_cases = existing_db.get('cases', [])
    existing_metadata = existing_db.get('metadata', {})

    # Load new
    with open(new_cases_path, 'r', encoding='utf-8') as f:
        new_db = json.load(f)

    new_cases = new_db.get('cases', [])
    new_metadata = new_db.get('metadata', {})

    # Deduplication
    existing_ids = {c['id'] for c in existing_cases}
    added = 0
    skipped = 0
    errors = 0

    for case in new_cases:
        errs = validate_case(case)
        if errs:
            print(f"  SKIP {case.get('name', '?')}: {', '.join(errs)}")
            errors += 1
            continue

        if case['id'] in existing_ids:
            skipped += 1
            continue

        existing_cases.append(case)
        existing_ids.add(case['id'])
        added += 1

    # Update metadata
    total_events = sum(len(c.get('events', [])) for c in existing_cases)
    known_hour = sum(1 for c in existing_cases if not c['birth'].get('hour_unknown'))

    existing_metadata.update({
        'version': '1.1',
        'last_merged': str(date.today()),
        'total_cases': len(existing_cases),
        'known_hour_cases': known_hour,
        'total_events': total_events,
        'sources': list(set(
            c.get('source', 'unknown') for c in existing_cases
        )),
    })

    output_db = {
        'metadata': existing_metadata,
        'cases': existing_cases,
    }

    if output_path is None:
        output_path = existing_path

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_db, f, ensure_ascii=False, indent=2)

    print(f"\nMerge complete:")
    print(f"  Added: {added}")
    print(f"  Skipped (duplicate): {skipped}")
    print(f"  Errors: {errors}")
    print(f"  Total cases: {len(existing_cases)}")
    print(f"  Known hour: {known_hour}")
    print(f"  Total events: {total_events}")
    print(f"  Output: {output_path}")

    return added, skipped, errors


def main():
    parser = argparse.ArgumentParser(description='Merge celebrity cases into case DB')
    parser.add_argument('--existing', default='cases_real_db.json',
                        help='Existing case DB JSON')
    parser.add_argument('--new', default='celebrity_cases.json',
                        help='New cases to merge')
    parser.add_argument('--output', '-o', default=None,
                        help='Output path (default: overwrite existing)')
    args = parser.parse_args()

    if not os.path.exists(args.existing):
        print(f"Existing DB not found: {args.existing}")
        # Create new DB from new cases
        with open(args.new, 'r', encoding='utf-8') as f:
            new_db = json.load(f)
        with open(args.output or args.existing, 'w', encoding='utf-8') as f:
            json.dump(new_db, f, ensure_ascii=False, indent=2)
        print(f"Created new DB from {args.new}")
        return

    merge_cases(args.existing, args.new, args.output)


if __name__ == '__main__':
    import argparse
    main()
