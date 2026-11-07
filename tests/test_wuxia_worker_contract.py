import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from wuxia_worker_contract import claim_acknowledgement

def test_native_support_is_acknowledged_for_each_new_lease():
 snapshot={'scenes':[{'wuxia_timeline':{'contract':'wuxia_native_timeline/v3'}}]}
 metadata={'input':{'required_worker_contract':'wuxia_native_timeline/v3'},'worker_contract_ack':{'lease_token':'stale'}}
 assert claim_acknowledgement(snapshot,metadata,'fresh')['worker_contract_ack']=={'contract':'wuxia_native_timeline/v3','lease_token':'fresh'}

def test_unknown_native_contract_is_never_treated_as_a_still():
 with pytest.raises(ValueError,match='Unsupported frozen'):
  claim_acknowledgement({'scenes':[{'wuxia_timeline':{'contract':'wuxia_native_timeline/v99'}}]}, {},'lease')

def test_other_productions_keep_existing_claim():
 assert claim_acknowledgement({'scenes':[{'source_kind':'image'}]}, {},'lease')=={}
