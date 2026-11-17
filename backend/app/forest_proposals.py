"""Public proposals for community forests that are not in the system yet.

Anyone may propose one (no account). The proposal is stored privately for the team to check;
nothing appears on the map until the team adds the forest. Limits live in the database function.
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.community_store import CommunityStore
from app.config import Settings, get_settings

router = APIRouter(prefix='/api/community', tags=['Community'])


class ForestProposal(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=120)
    village: str = Field(default='', max_length=120)
    tambon: str = Field(default='', max_length=80)
    district: str = Field(default='', max_length=80)
    # Chiang Mai and its edges only, the same box the report forms use.
    latitude: float = Field(ge=17, le=21)
    longitude: float = Field(ge=97.3, le=100)
    details: str = Field(default='', max_length=1000)
    proposer_name: str = Field(default='', max_length=80)
    contact_phone: str | None = Field(default=None, max_length=20, pattern=r'^[0-9+()\- ]{6,20}$')


def sender_hash(request: Request, settings: Settings) -> str:
    """A salted hash of the sender's address: enough to rate-limit, never stored as the address."""
    forwarded = request.headers.get('x-forwarded-for', '').split(',')[0].strip()
    address = forwarded or (request.client.host if request.client else 'unknown')
    salt = settings.supabase_service_role_key or 'chiangmaieyes'
    return hashlib.sha256((salt + '|forest-proposal|' + address).encode()).hexdigest()


@router.post('/forest-proposals', status_code=201)
def propose_forest(payload: ForestProposal, request: Request, settings: Settings = Depends(get_settings)):
    store = CommunityStore(settings)
    proposal_id = store.call('POST', '/rest/v1/rpc/cme_propose_forest',
                             json={'p': payload.model_dump(), 'p_ip_hash': sender_hash(request, settings)})
    return {'id': proposal_id, 'status': 'pending'}
