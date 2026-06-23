#!/usr/bin/env python3
"""
Assign microservices to zones and produce a zoned microservices CSV.

Defaults mapping (can be overridden with --rules JSON):
- APP-EME -> ZEMG
- APP-TEL -> ZPIT
- APP-COM, APP-RET, APP-SYS -> ZSTART

Writes `data/microservicios_zonificados.csv` by default.
"""
import csv
import argparse
import json
from collections import Counter


def load_zones(zones_csv):
    zones = set()
    with open(zones_csv, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            zid = r.get('zone_id')
            if zid:
                zones.add(zid)
    return zones


def default_rules():
    return {
        'APP-EME': 'ZEMG',
        'APP-TEL': 'ZPIT',
        'APP-COM': 'ZSTART',
        'APP-RET': 'ZSTART',
        'APP-SYS': 'ZSTART',
    }


def assign_zone(row, rules, zones):
    app_id = row.get('app_id', '')
    # try exact prefix match
    for prefix, zid in rules.items():
        if app_id.startswith(prefix):
            # only assign if zone exists in zones file
            if zid in zones:
                return zid
    return ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--microservices', default='data/microservicios.csv')
    parser.add_argument('--zones', default='data/superficie_zonas.csv')
    parser.add_argument('--out', default='data/microservicios_zonificados.csv')
    parser.add_argument('--rules', help='Optional JSON file with mapping prefix->zone_id')
    args = parser.parse_args()

    zones = load_zones(args.zones)
    rules = default_rules()
    if args.rules:
        with open(args.rules, encoding='utf-8') as rf:
            rules.update(json.load(rf))

    rows = []
    counter = Counter()
    with open(args.microservices, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames[:] if reader.fieldnames else []
        if 'zone_id' not in fieldnames:
            fieldnames.append('zone_id')
        # mark whether service is callable from the circuit (global access)
        if 'callable_from_circuit' not in fieldnames:
            fieldnames.append('callable_from_circuit')
        for r in reader:
            zid = assign_zone(r, rules, zones)
            r['zone_id'] = zid
            # By policy: all microservices must be callable from anywhere on the circuit
            r['callable_from_circuit'] = 'YES'
            rows.append(r)
            counter[zid or 'UNASSIGNED'] += 1

    with open(args.out, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print('Wrote', args.out)
    print('Summary:')
    for zid, cnt in counter.items():
        print(f'  {zid}: {cnt}')


if __name__ == '__main__':
    main()
