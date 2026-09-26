"""Resolve one effective revision per external source identity."""
from fastapi import HTTPException


def effective_versions(rows,key):
    latest={}
    for row in rows:
        identity=key(row)
        prior=latest.get(identity)
        if prior and prior.source_revision==row.source_revision and prior.id!=row.id:
            raise HTTPException(409,'AMBIGUOUS_SOURCE_REVISION')
        if not prior or row.source_revision>prior.source_revision:latest[identity]=row
    return list(latest.values())
